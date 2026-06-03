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
    to_thread.current_default_thread_limiter().total_tokens = 8
    
    init_db()
    # Explicit garbage collection to free up memory
    gc.collect()


# Dimensione ottimizzata per massimizzare throughput I/O senza pesare sulla RAM
CHUNK_SIZE = 1024 * 1024  # 1 MB chunk

class ChunkedRangeStaticFiles(StaticFiles):
    """
    StaticFiles che serve i range request leggendo sempre a chunk di dimensione fissa,
    garantendo uso di memoria O(1). Gestisce proattivamente i disconnect del client
    (es. seek o stop riproduzione) per rilasciare i file descriptor e fermare i thread di I/O.
    """
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await super().__call__(scope, receive, send)
            return

        path = self.get_path(scope)
        full_path, stat_result = await self.lookup_path(path)

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
                s, e = range_spec.split("-")
                start = int(s) if s else 0
                end = int(e) if e else file_size - 1
                status_code = 206
            except Exception:
                pass

        # Gestione di range requests invalidi
        if start >= file_size or end >= file_size or start > end:
            await send({
                "type": "http.response.start",
                "status": 416,
                "headers": [(b"content-range", f"bytes */{file_size}".encode())],
            })
            await send({"type": "http.response.body", "body": b""})
            return

        content_length = end - start + 1

        import mimetypes
        content_type, _ = mimetypes.guess_type(str(full_path))
        content_type = content_type or "application/octet-stream"

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
                # Sia eventuali error ASGI che CancelledError da anyio
                pass

        async def send_file():
            try:
                bytes_sent = 0
                # anyio.open_file utilizza thread asincroni poolati, ideale per I/O da disco
                async with await anyio.open_file(full_path, "rb") as f:
                    await f.seek(start)
                    while bytes_sent < content_length and not client_disconnected.is_set():
                        chunk_size = min(CHUNK_SIZE, content_length - bytes_sent)
                        chunk = await f.read(chunk_size)
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
            except Exception:
                pass
            finally:
                client_disconnected.set()

        # Isoliamo l'operazione in un task group per gestire parallelamente I/O e disconnessioni
        async with anyio.create_task_group() as tg:
            tg.start_soon(listen_for_disconnect)
            await send_file()
            # Finito il file (o interrotto), cancelliamo listen_for_disconnect
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

# Redirect root to file browser (already covered by admin_router's @router.get("/") if we add it)
# Or just define it here.
@app.get("/")
def root(request: Request):
    ingress_path = request.headers.get("X-Ingress-Path", "")
    return RedirectResponse(url=f"{ingress_path}/files")
