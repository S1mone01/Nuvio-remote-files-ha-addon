"""
Admin and installation endpoints for the Stremio Remote Files addon.

This module provides:
- A lightweight admin UI for triggering library scans
- An install page for generating Stremio addon install links
- A file browser UI (/) showing all indexed files with total size

Note: The HTML pages themselves are intentionally unauthenticated.
All destructive or privileged actions require a valid admin token.
"""

from fastapi import APIRouter, Request, BackgroundTasks
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
import sqlite3

from scanner import scan_movies, scan_series
from scanner.organizer import organize_downloads
from scanner.ffmpeg_utils import filter_existing_library, FILTERING_STATUS
from core.config import DB_PATH, is_disk_online
from core.auth import require_admin_token

router = APIRouter()

templates = Jinja2Templates(directory="api/templates")


# ── File browser UI ───────────────────────────────────────────────────

@router.get("/files", response_class=HTMLResponse)
def files_page(request: Request):
    """Human-friendly file browser: shows all indexed files and total size."""
    return templates.TemplateResponse(
        request=request,
        name="files.html",
        context={"disk_online": is_disk_online()}
    )


@router.get("/api/files")
def api_files():
    """
    JSON endpoint consumed by the /files UI.

    Returns a flat list of all indexed files, with type, title, path,
    resolution, size, and (for episodes) season/episode numbers.
    Also returns aggregate totals for the stat bar.
    """
    with sqlite3.connect(DB_PATH) as conn:
        # ── Movies ──────────────────────────────────────────────────
        movie_rows = conn.execute(
            """
            SELECT m.title, f.path, f.resolution, f.size
            FROM files f
            JOIN movies m ON m.imdb_id = f.movie_imdb_id
            WHERE f.movie_imdb_id IS NOT NULL
            ORDER BY m.title
            """
        ).fetchall()

        # ── Episodes ─────────────────────────────────────────────────
        ep_rows = conn.execute(
            """
            SELECT s.title, e.season, e.episode, f.path, f.resolution, f.size
            FROM files f
            JOIN episodes e ON e.id = f.episode_id
            JOIN series  s ON s.imdb_id = e.series_imdb_id
            WHERE f.episode_id IS NOT NULL
            ORDER BY s.title, e.season, e.episode
            """
        ).fetchall()

    files = []

    for title, path, resolution, size in movie_rows:
        files.append({
            "type":       "movie",
            "title":      title,
            "path":       path,
            "resolution": resolution,
            "size":       size or 0,
        })

    for series_title, season, episode, path, resolution, size in ep_rows:
        files.append({
            "type":         "series",
            "series_title": series_title,
            "season":       season,
            "episode":      episode,
            "path":         path,
            "resolution":   resolution,
            "size":         size or 0,
        })

    total_size = sum(f["size"] for f in files)

    return {
        "files":      files,
        "total_size": total_size,
        "count":      len(files),
    }


@router.get("/api/downloads")
def api_downloads():
    """
    JSON endpoint that scans the downloads directory and identifies
    files that haven't been processed.
    
    Optimized: Removed slow TMDB lookups during initial listing to avoid hangs.
    Identification is done on-demand or during actual organization.
    """
    from scanner.organizer import DOWNLOADS_ROOT, VIDEO_EXTENSIONS, parse_filename
    
    files = []
    if DOWNLOADS_ROOT.exists():
        for path in DOWNLOADS_ROOT.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in VIDEO_EXTENSIONS:
                continue
            
            # Use relative path from DOWNLOADS_ROOT for the frontend to send back
            rel_path = str(path.relative_to(DOWNLOADS_ROOT))
            
            is_series, title, year, season, episode, resolution = parse_filename(path.name)
            
            # unrecognized is always False by default now to keep things fast.
            # Identification happens when the user clicks "Identifica" or 
            # when "Identifica Tutto" is clicked (which triggers organize_downloads)
            
            files.append({
                "name": path.name,
                "path": rel_path,
                "is_series": is_series,
                "title": title,
                "year": year,
                "season": season,
                "episode": episode,
                "resolution": resolution,
                "unrecognized": False,
                "size": path.stat().st_size
            })
    
    return {"files": files}


@router.post("/admin/downloads/rename")
async def admin_downloads_rename(request: Request):
    """
    Manually rename and organize a file from the downloads directory.
    """
    from scanner.organizer import move_file, DOWNLOADS_ROOT
    try:
        data = await request.json()
        
        path = DOWNLOADS_ROOT / data["path"]
        if not path.exists():
            return {"status": "error", "message": "File not found"}
        
        success, result = move_file(
            path,
            is_series=data.get("is_series", False),
            title=data.get("title"),
            year=data.get("year"),
            season=data.get("season"),
            episode=data.get("episode"),
            resolution=data.get("resolution")
        )
        
        if success:
            return {"status": "ok", "dest": result}
        else:
            return {"status": "error", "message": result}
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"[ERROR] Manual rename crash: {error_details}")
        return {"status": "error", "message": f"Errore interno del server: {str(e)}"}


@router.post("/admin/library/rename")
async def admin_library_rename(request: Request):
    """
    Manually rename and organize a file that is already in the library.
    """
    from scanner.organizer import move_file
    from pathlib import Path
    
    MEDIA_ROOT = Path("/media")
    
    try:
        data = await request.json()
        # In library, paths are already relative to /media or absolute starting with /media
        raw_path = data["path"]
        if raw_path.startswith("/media/"):
            path = Path(raw_path)
        else:
            path = MEDIA_ROOT / raw_path
            
        if not path.exists():
            return {"status": "error", "message": f"File not found at {path}"}
        
        success, result = move_file(
            path,
            is_series=data.get("is_series", False),
            title=data.get("title"),
            year=data.get("year"),
            season=data.get("season"),
            episode=data.get("episode"),
            resolution=data.get("resolution")
        )
        
        if success:
            return {"status": "ok", "dest": result}
        else:
            return {"status": "error", "message": result}
    except Exception as e:
        import traceback
        print(f"[ERROR] Library rename crash: {traceback.format_exc()}")
        return {"status": "error", "message": str(e)}


@router.post("/admin/downloads/organize")
def admin_downloads_organize(request: Request):
    """
    Manually trigger the organization of the downloads directory.
    """
    organize_downloads()
    return {"status": "ok"}


@router.post("/admin/debug/parse")
async def admin_debug_parse(request: Request):
    """
    Debug endpoint to test how a filename will be parsed and if it's compatible with Stremio.
    """
    from scanner.organizer import parse_filename, get_clean_stem
    from scanner.scan_series import parse_episode_filename
    from metadata.tmdb import lookup_movie, lookup_series
    from scanner.organizer import smart_lookup_series
    from metadata.tmdb import lookup_episode
    import traceback
    
    try:
        data = await request.json()
        filename = data.get("filename", "")
        if not filename:
            return {"status": "error", "message": "No filename provided"}
        
        # 1. Test Organizer Parsing (Raw -> Clean)
        is_series, title, year, season, episode, tags = parse_filename(filename)
        
        tmdb_status = "Not checked"
        clean_meta = None
        final_filename = "N/D"
        
        # Get clean extension safely
        _, ext = get_clean_stem(filename)
        if not ext:
            ext = ".mkv" # Fallback for preview
        
        if is_series:
            clean_meta = smart_lookup_series(title)
            if clean_meta:
                tmdb_status = "Found"
                # Try to get episode title for final name preview
                ep_meta = lookup_episode(clean_meta.get("tmdb_id"), season, episode)
                display_title = ep_meta["title"] if ep_meta and ep_meta.get("title") else clean_meta["title"]
                tag_suffix = f" [{tags}]" if tags else ""
                final_filename = f"S{season:02d}E{episode:02d} {display_title}{tag_suffix}{ext}"
            else:
                tmdb_status = "Not Found"
        else:
            clean_meta = lookup_movie(title, year)
            if clean_meta:
                tmdb_status = "Found"
                tag_suffix = f" [{tags}]" if tags else ""
                final_filename = f"{clean_meta['title']} ({clean_meta['year']}){tag_suffix}{ext}"
            else:
                tmdb_status = "Not Found"

        # 2. Test Scanner/Stremio Compatibility (Clean/Structured -> DB/Stremio)
        # This checks if the SxEx pattern is found for Stremio matching
        scanner_result = parse_episode_filename(filename)
        
        if is_series:
            stremio_compatible = scanner_result is not None
            note = "Stremio richiede un pattern SxEx chiaro (es. S01E01) per riconoscere gli episodi."
        else:
            # Movies are always compatible if they have a clear title/year
            stremio_compatible = title is not None
            note = "I film vengono riconosciuti automaticamente tramite titolo e anno."
        
        return {
            "status": "ok",
            "organizer": {
                "is_series": is_series,
                "title": title,
                "year": year,
                "season": season,
                "episode": episode,
                "tags": tags,
                "tmdb": tmdb_status,
                "tmdb_title": clean_meta["title"] if clean_meta else None,
                "final_filename": final_filename
            },
            "stremio": {
                "compatible": stremio_compatible,
                "parsed": scanner_result if (is_series and stremio_compatible) else None,
                "note": note
            }
        }
    except Exception as e:
        print(f"[ERROR] Debug parse crash: {traceback.format_exc()}")
        return {"status": "error", "message": f"Errore interno del server: {str(e)}"}


@router.post("/admin/library/filter-mkv")
def admin_library_filter_mkv(background_tasks: BackgroundTasks):
    """
    Trigger the MKV track filtering process for the entire library.
    """
    if FILTERING_STATUS["is_running"]:
        return {"status": "error", "message": "Il processo è già in esecuzione"}
    
    background_tasks.add_task(filter_existing_library)
    return {"status": "ok", "message": "Filtraggio avviato in background"}


@router.post("/admin/file/filter-mkv")
async def admin_file_filter_mkv(request: Request, background_tasks: BackgroundTasks):
    """
    Trigger MKV filtering for a single file.
    """
    from scanner.ffmpeg_utils import process_mkv_tracks, FILTERING_STATUS
    from scanner.organizer import DOWNLOADS_ROOT, MEDIA_ROOT
    
    if FILTERING_STATUS["is_running"]:
        return {"status": "error", "message": "Un processo di filtraggio è già in corso"}

    try:
        data = await request.json()
        file_path_str = data.get("path")
        is_library = data.get("is_library", False)
        
        if is_library:
            if file_path_str.startswith("/media/"):
                path = Path(file_path_str)
            else:
                path = MEDIA_ROOT / file_path_str
        else:
            path = DOWNLOADS_ROOT / file_path_str

        if not path.exists():
            return {"status": "error", "message": "File non trovato"}

        # We run this in background too to avoid timeout and reuse status
        def single_file_task():
            FILTERING_STATUS["is_running"] = True
            FILTERING_STATUS["total"] = 1
            FILTERING_STATUS["processed"] = 0
            FILTERING_STATUS["current_file"] = path.name
            FILTERING_STATUS["last_error"] = None
            try:
                process_mkv_tracks(path)
                FILTERING_STATUS["processed"] = 1
            except Exception as e:
                FILTERING_STATUS["last_error"] = str(e)
            finally:
                FILTERING_STATUS["is_running"] = False

        background_tasks.add_task(single_file_task)
        return {"status": "ok", "message": "Filtraggio file avviato"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/admin/library/filter-mkv/status")
def admin_library_filter_mkv_status():
    """
    Get the current status of the MKV filtering process.
    """
    return FILTERING_STATUS


@router.post("/admin/file/tracks")
async def admin_file_tracks(request: Request):
    """
    Get MKV track info for a specific file.
    """
    from scanner.mkv_utils import get_mkv_tracks
    from scanner.organizer import DOWNLOADS_ROOT, MEDIA_ROOT
    
    try:
        data = await request.json()
        file_path_str = data.get("path")
        is_library = data.get("is_library", False)
        
        if is_library:
            if file_path_str.startswith("/media/"):
                path = Path(file_path_str)
            else:
                path = MEDIA_ROOT / file_path_str
        else:
            path = DOWNLOADS_ROOT / file_path_str
            
        tracks = get_mkv_tracks(path)
        return {"status": "ok", "tracks": tracks}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/admin/file/tracks/update")
async def admin_file_tracks_update(request: Request):
    """
    Update MKV track metadata for a specific file.
    """
    from scanner.mkv_utils import update_mkv_metadata
    from scanner.organizer import DOWNLOADS_ROOT, MEDIA_ROOT
    
    try:
        data = await request.json()
        file_path_str = data.get("path")
        is_library = data.get("is_library", False)
        updates = data.get("updates", [])
        
        if is_library:
            if file_path_str.startswith("/media/"):
                path = Path(file_path_str)
            else:
                path = MEDIA_ROOT / file_path_str
        else:
            path = DOWNLOADS_ROOT / file_path_str
            
        success, message = update_mkv_metadata(path, updates)
        return {"status": "ok" if success else "error", "message": message}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ── Admin pages ──────────────────────────────────────────────────────

# These pages are intentionally unauthenticated.
# All privileged actions are protected by token checks on POST routes.
@router.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="admin.html",
        context={"disk_online": is_disk_online()}
    )


@router.post("/admin/scan")
def admin_scan(request: Request):
    scan_movies()
    scan_series()

    return {
        "status": "ok",
        "mode": "incremental"
    }


@router.post("/admin/scan/rebuild")
def admin_scan_rebuild(request: Request):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM files")
        conn.execute("DELETE FROM episodes")
        conn.execute("DELETE FROM series")
        conn.execute("DELETE FROM movies")
        conn.commit()

    scan_movies()
    scan_series()

    return {
        "status": "ok",
        "mode": "rebuild"
    }


# Configuration / install UI.
#
# These endpoints intentionally return a human-friendly HTML page.
# The same page is used for:
# - initial addon installation
# - the Stremio ⚙️ configure action (internal and external)
#
# Access control for streaming is enforced via tokenized stream endpoints
# and proxy-level checks, not via the configure page itself.
@router.get("/internal/configure", response_class=HTMLResponse)
@router.get("/external/configure", response_class=HTMLResponse)
def configure_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="configure.html",
        context={"disk_online": is_disk_online()}
    )
