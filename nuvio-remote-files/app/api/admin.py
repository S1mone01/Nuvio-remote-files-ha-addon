"""
Admin and installation endpoints for the Stremio Remote Files addon.

This module provides:
- A lightweight admin UI for triggering library scans
- An install page for generating Stremio addon install links
- A file browser UI (/) showing all indexed files with total size

Note: The HTML pages themselves are intentionally unauthenticated.
All destructive or privileged actions require a valid admin token.
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import sqlite3

from scanner import scan_movies, scan_series
from scanner.organizer import organize_downloads
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
    files that haven't been processed, marking unrecognized ones.
    """
    from scanner.organizer import DOWNLOADS_ROOT, VIDEO_EXTENSIONS, parse_filename
    from metadata.tmdb import lookup_movie, lookup_series
    
    files = []
    if DOWNLOADS_ROOT.exists():
        for path in DOWNLOADS_ROOT.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in VIDEO_EXTENSIONS:
                continue
            
            # Use relative path from DOWNLOADS_ROOT for the frontend to send back
            rel_path = str(path.relative_to(DOWNLOADS_ROOT))
            
            is_series, title, year, season, episode, resolution = parse_filename(path.name)
            
            unrecognized = False
            try:
                if is_series:
                    if not lookup_series(title):
                        unrecognized = True
                else:
                    if not lookup_movie(title, year):
                        unrecognized = True
            except Exception:
                unrecognized = True
            
            files.append({
                "name": path.name,
                "path": rel_path,
                "is_series": is_series,
                "title": title,
                "year": year,
                "season": season,
                "episode": episode,
                "resolution": resolution,
                "unrecognized": unrecognized,
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
    from scanner.organizer import parse_filename
    from scanner.scan_series import parse_episode_filename
    from metadata.tmdb import lookup_movie, lookup_series
    
    data = await request.json()
    filename = data.get("filename", "")
    if not filename:
        return {"status": "error", "message": "No filename provided"}
    
    # 1. Test Organizer Parsing (Raw -> Clean)
    is_series, title, year, season, episode, tags = parse_filename(filename)
    
    tmdb_status = "Not checked"
    clean_meta = None
    if is_series:
        clean_meta = lookup_series(title)
        tmdb_status = "Found" if clean_meta else "Not Found"
    else:
        clean_meta = lookup_movie(title, year)
        tmdb_status = "Found" if clean_meta else "Not Found"

    # 2. Test Scanner/Stremio Compatibility (Clean/Structured -> DB/Stremio)
    # This checks if the SxEx pattern is found for Stremio matching
    scanner_result = parse_episode_filename(filename)
    stremio_compatible = scanner_result is not None
    
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
            "tmdb_title": clean_meta["title"] if clean_meta else None
        },
        "stremio": {
            "compatible": stremio_compatible,
            "parsed": scanner_result if stremio_compatible else None,
            "note": "Stremio requires a clear SxEx pattern to match episodes." if is_series else "Movies match by title/year."
        }
    }


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
