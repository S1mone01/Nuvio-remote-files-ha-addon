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
from core.config import DB_PATH
from core.auth import require_admin_token

router = APIRouter()

templates = Jinja2Templates(directory="api/templates")


# ── File browser UI ───────────────────────────────────────────────────

@router.get("/files", response_class=HTMLResponse)
def files_page(request: Request):
    """Human-friendly file browser: shows all indexed files and total size."""
    return templates.TemplateResponse(
        "files.html",
        {"request": request}
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


# ── Admin pages ──────────────────────────────────────────────────────

# These pages are intentionally unauthenticated.
# All privileged actions are protected by token checks on POST routes.
@router.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request):
    return templates.TemplateResponse(
        "admin.html",
        {"request": request}
    )


@router.post("/admin/scan")
def admin_scan(request: Request):
    require_admin_token(request)

    scan_movies()
    scan_series()

    return {
        "status": "ok",
        "mode": "incremental"
    }


@router.post("/admin/scan/rebuild")
def admin_scan_rebuild(request: Request):
    require_admin_token(request)

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
        "configure.html",
        {"request": request}
    )
