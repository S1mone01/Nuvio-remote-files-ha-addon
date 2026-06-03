"""
Application entry point.

This module creates the FastAPI app, initializes the database on startup,
and wires together the API routers.
"""

import threading
import gc

# Set a smaller thread stack size to save virtual memory on constrained systems.
# Default is usually 8MB; 512KB is plenty for these I/O tasks.
try:
    threading.stack_size(1024 * 512)
except ValueError:
    # Some platforms might not support changing stack size after threads have started
    pass

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from anyio import to_thread

from db.init import init_db
from api.stremio import router as stremio_router
from api.admin import router as admin_router
from api.auth import router as auth_router
from scanner import scan_movies, scan_series
from scanner.organizer import organize_downloads

app = FastAPI()

# Stremio desktop/web clients require permissive CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
)


@app.on_event("startup")
async def startup():
    """
    Initialize the database schema and limit worker threads at application startup.
    """
    # Limit anyio worker threads to prevent OOM on constrained systems
    # each thread consumes memory for its stack and I/O buffer.
    # On systems with more RAM (like 8GB), we can allow more threads to 
    # handle concurrent file I/O for streaming more efficiently.
    to_thread.current_default_thread_limiter().total_tokens = 8
    
    init_db()
    # Explicit garbage collection to free up memory
    gc.collect()


# Custom StaticFiles implementation that uses a smaller chunk size (16KB vs 64KB)
# to minimize memory spikes during concurrent range requests (seeking).
class MemoryEfficientFileResponse(FileResponse):
    chunk_size = 1024 * 16

class MemoryEfficientStaticFiles(StaticFiles):
    def file_response(self, full_path, stat_result, scope, status_code=200):
        return MemoryEfficientFileResponse(
            full_path, stat_result=stat_result, scope=scope, status_code=status_code
        )


# Public Stremio addon endpoints
app.include_router(stremio_router)

# Admin and install endpoints
app.include_router(admin_router)

# Auth endpoints
app.include_router(auth_router)

# Serve static media files using the memory-efficient implementation
app.mount("/media", MemoryEfficientStaticFiles(directory="/media"), name="media")



# Redirect /manifest.json to internal manifest
@app.get("/manifest.json")
def manifest_redirect(request: Request):
    ingress_path = request.headers.get("X-Ingress-Path", "")
    return RedirectResponse(url=f"{ingress_path}/internal/manifest.json")

# Redirect root to file browser (already covered by admin_router's @router.get("/") if we add it)
# Or just define it here.
@app.get("/")
def root(request: Request):
    ingress_path = request.headers.get("X-Ingress-Path", "")
    return RedirectResponse(url=f"{ingress_path}/files")
