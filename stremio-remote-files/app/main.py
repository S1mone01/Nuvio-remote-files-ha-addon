"""
Application entry point.

This module creates the FastAPI app, initializes the database on startup,
and wires together the API routers.
"""

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware

from fastapi.staticfiles import StaticFiles
from db.init import init_db
from api.stremio import router as stremio_router
from api.admin import router as admin_router
from api.auth import router as auth_router
from scanner import scan_movies, scan_series

app = FastAPI()

# Redirect root to library page
@app.get("/")
def root():
    return RedirectResponse(url="/library")

# Redirect /manifest.json to internal manifest
@app.get("/manifest.json")
def manifest_redirect():
    return RedirectResponse(url="/internal/manifest.json")

# Stremio desktop/web clients require permissive CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
)


@app.on_event("startup")
def startup():
    """
    Initialize the database schema at application startup.
    """
    init_db()

    # Initial library scan (runs once on startup)
    scan_movies()
    scan_series()


# Public Stremio addon endpoints
app.include_router(stremio_router)

# Admin and install endpoints
app.include_router(admin_router)

# Auth endpoints
app.include_router(auth_router)

# Serve static media files (replaces Caddy's file_server)
# Must be mounted last so it doesn't shadow API routes
app.mount("/", StaticFiles(directory="/media"), name="media")