"""
Application entry point.

This module creates the FastAPI app, initializes the database on startup,
and wires together the API routers.
"""

import threading
import gc
import os
import stat

# Set a smaller thread stack size to save virtual memory on constrained systems.
# Default is usually 8MB; 512KB is plenty for these I/O tasks.
try:
    threading.stack_size(1024 * 512)
except ValueError:
    # Some platforms might not support changing stack size after threads have started
    pass

from fastapi import FastAPI, Request, Response
from fastapi.responses import RedirectResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import anyio
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
    to_thread.current_default_thread_limiter().total_tokens = 20

    init_db()
    # Explicit garbage collection to free up memory
    gc.collect()


# Leggi sempre a chunk piccoli anche all'interno di un range:
CHUNK_SIZE = 1024 * 64  # 64 KB — abbastanza piccolo, abbastanza veloce

class ChunkedRangeStaticFiles(StaticFiles):
    """
    StaticFiles che serve i range request leggendo sempre a chunk piccoli,
    invece di fare un unico read() sull'intero range (che causa OOM su seek).
    """
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await super().__call__(scope, receive, send)
            return

        path = self.get_path(scope)
        full_path, stat_result = self.lookup_path(path)

        if stat_result is None or not stat.S_ISREG(stat_result.st_mode):
            await super().__call__(scope, receive, send)
            return

        # Leggi gli header della richiesta
        headers = dict(scope.get("headers", []))
        range_header = headers.get(b"range", b"").decode()

        file_size = stat_result.st_size
        start = 0
        end = file_size - 1
        status_code = 200

        if range_header.startswith("bytes="):
            try:
                range_spec = range_header[6:]
                if "-" in range_spec:
                    s, e = range_spec.split("-")
                    if s:
                        start = int(s)
                        if e:
                            end = int(e)
                    elif e:
                        # Suffix-byte-range: last N bytes
                        start = max(0, file_size - int(e))
                status_code = 206
            except Exception as e:
                logging.error(f"[STREAM] Error parsing range header '{range_header}': {e}")

        # Assicura che i range siano validi
        start = max(0, min(start, file_size - 1))
        end = max(start, min(end, file_size - 1))
        content_length = end - start + 1

        # Determina il content-type in base all'estensione
        ext = os.path.splitext(full_path)[1].lower()
        mime_types = {
            ".mp4": "video/mp4",
            ".mkv": "video/x-matroska",
            ".webm": "video/webm",
            ".avi": "video/x-msvideo",
            ".mov": "video/quicktime",
            ".m4v": "video/x-m4v"
        }
        content_type = mime_types.get(ext, "video/x-matroska")

        response_headers = [
            (b"content-type", content_type.encode()),
            (b"content-length", str(content_length).encode()),
            (b"accept-ranges", b"bytes"),
            (b"content-range", f"bytes {start}-{end}/{file_size}".encode()),
        ]

        await send({
            "type": "http.response.start",
            "status": status_code,
            "headers": response_headers,
        })

        client_disconnected = anyio.Event()

        async def listen_for_disconnect():
            try:
                while True:
                    message = await receive()
                    if message["type"] == "http.disconnect":
                        client_disconnected.set()
                        break
            except Exception:
                pass

        async def send_file():
            try:
                bytes_sent = 0
                async with await anyio.open_file(full_path, "rb") as f:
                    await f.seek(start)
                    while bytes_sent < content_length and not client_disconnected.is_set():
                        chunk = await f.read(min(CHUNK_SIZE, content_length - bytes_sent))
                        if not chunk:
                            break
                        
                        if client_disconnected.is_set():
                            break

                        await send({
                            "type": "http.response.body",
                            "body": chunk,
                            "more_body": (bytes_sent + len(chunk)) < content_length,
                        })
                        bytes_sent += len(chunk)
            except Exception as e:
                logging.error(f"[STREAM] Error sending file {full_path}: {e}")
            finally:
                client_disconnected.set()

        # Usiamo un task group per gestire parallelamente l'invio e l'ascolto della disconnessione
        async with anyio.create_task_group() as tg:
            tg.start_soon(listen_for_disconnect)
            await send_file()
            tg.cancel_scope.cancel()


# Public Stremio addon endpoints
app.include_router(stremio_router)

# Admin and install endpoints
app.include_router(admin_router)

# Auth endpoints
app.include_router(auth_router)

# Serve static media files using the memory-efficient implementation
app.mount("/media", ChunkedRangeStaticFiles(directory="/media"), name="media")


# Redirect /manifest.json to internal manifest
@app.get("/manifest.json")
def manifest_redirect(request: Request):
    ingress_path = request.headers.get("X-Ingress-Path", "")
    return RedirectResponse(url=f"{ingress_path}/internal/manifest.json")
