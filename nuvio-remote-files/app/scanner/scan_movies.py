"""
Movie filesystem scanner.

This module scans the movies directory, resolves metadata via TMDB,
and synchronizes movie and file records into the SQLite database.
"""

from pathlib import Path
import re
import sqlite3
import logging

from core.config import MOVIES_DIR_NAME
from scanner.utils import extract_tags, clean_name
from metadata.tmdb import lookup_movie
from db.movie_repo import upsert_movie, upsert_movie_file

# Root directory for movie files (mounted volume)
MOVIES_ROOT = Path("/media") / MOVIES_DIR_NAME

# SQLite database location
DB_PATH = "/data/library.db"

def scan_movies():
    """
    Scan the movie directory and synchronize database records.

    - Discovers movie files on disk
    - Looks up metadata via TMDB
    - Inserts or updates movie and file records
    - Removes database entries for files no longer present
    """
    if not MOVIES_ROOT.exists():
        logging.warning(f"[WARN] Movies directory not found: {MOVIES_ROOT}")
        return

    conn = sqlite3.connect(DB_PATH)
    seen_paths = set()

    # Regex for extracting title and year from standardized format: Title (YYYY) [Tags].ext
    PARSER_PATTERN = re.compile(r"^(?P<title>.+?)\s*\((?P<year>\d{4})\)", re.IGNORECASE)

    try:
        for path in MOVIES_ROOT.iterdir():
            if not path.is_file():
                continue

            # Skip common non-video files
            if path.suffix.lower() not in {".mkv", ".mp4", ".avi", ".mov", ".m4v", ".wmv"}:
                continue

            match = PARSER_PATTERN.match(path.name)
            if not match:
                logging.info(f"[SKIP] Unrecognized movie filename: {path.name}")
                continue

            title = clean_name(match.group("title"))
            year = int(match.group("year"))
            
            # Extract tags using centralized logic
            tags = extract_tags(path.name)

            logging.info(f"[INFO] TMDB lookup: {title} ({year})")
            meta = lookup_movie(title, year)

            if not meta:
                logging.warning(f"[WARN] TMDB lookup failed: {title}")
                continue

            # Track file as seen for cleanup
            seen_paths.add(str(path))

            # 1) Upsert movie metadata
            upsert_movie(conn, meta)

            # 2) Upsert file record
            upsert_movie_file(
                conn,
                imdb_id=meta["imdb_id"],
                path=str(path),
                resolution=tags, # Using resolution column for all tags
                size=path.stat().st_size,
            )

        # 3) Delete movie files no longer present on disk
        if seen_paths:
            placeholders = ",".join("?" * len(seen_paths))
            conn.execute(
                f"""
                DELETE FROM files
                WHERE movie_imdb_id IS NOT NULL
                  AND path NOT IN ({placeholders})
                """,
                tuple(seen_paths),
            )

        conn.commit()
        logging.info("[OK] Movie scan complete")

    finally:
        conn.close()
