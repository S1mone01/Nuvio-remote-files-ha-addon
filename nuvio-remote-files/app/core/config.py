"""
Application configuration.

This module centralizes environment-based configuration for the
Stremio Remote Files addon, including database paths, media base URLs,
and access tokens.
"""

import os
import sqlite3
from datetime import datetime
from pathlib import Path

# SQLite database location (mounted volume)
DB_PATH = "/data/library.db"

# Media disk name for online check
MEDIA_DISK_NAME = os.getenv("MEDIA_DISK_NAME")

# Base URLs for serving media
MEDIA_BASE_URL_INTERNAL = os.getenv("MEDIA_BASE_URL_INTERNAL")
MEDIA_BASE_URL_EXTERNAL = os.getenv("MEDIA_BASE_URL_EXTERNAL")

# Stream provider display names shown in Stremio
STREAM_PROVIDER_NAME_INTERNAL = os.getenv(
    "STREAM_PROVIDER_NAME_INTERNAL",
    "Locale",
)

STREAM_PROVIDER_NAME_EXTERNAL = os.getenv(
    "STREAM_PROVIDER_NAME_EXTERNAL",
    "Locale",
)

# Stream resolver tokens (external playback)
RAW_STREAM_TOKENS = os.getenv("STREAM_TOKENS", "")
STREAM_TOKENS = {t.strip() for t in RAW_STREAM_TOKENS.split(",") if t.strip()}

# Admin scan token (admin actions only)
ADMIN_SCAN_TOKEN = os.getenv("ADMIN_SCAN_TOKEN")

# Media subfolder names under /media
MOVIES_DIR_NAME = os.getenv("MOVIES_DIR_NAME", "movies")
SERIES_DIR_NAME = os.getenv("SERIES_DIR_NAME", "series")
DOWNLOADS_DIR_NAME = os.getenv("DOWNLOADS_DIR_NAME", "downloads")

# MKV track filtering configuration
FILTER_MKV_TRACKS = os.getenv("FILTER_MKV_TRACKS", "false").lower() == "true"


def is_disk_online() -> bool:
    """
    Check if the media disk is currently mounted and accessible.
    Updates the cached status in the database.
    """
    if not MEDIA_DISK_NAME:
        return True

    disk_path = Path("/media") / MEDIA_DISK_NAME
    online = False
    try:
        # A disk is considered online if its mount directory exists and is not empty
        online = disk_path.exists() and disk_path.is_dir() and any(disk_path.iterdir())
    except (PermissionError, OSError):
        online = False

    # Update cache in DB
    try:
        with sqlite3.connect(DB_PATH) as conn:
            now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
            conn.execute(
                "UPDATE system_state SET value = ?, updated_at = CURRENT_TIMESTAMP WHERE key = 'disk_online'",
                (str(online).lower(),)
            )
            conn.execute(
                "UPDATE system_state SET value = ?, updated_at = CURRENT_TIMESTAMP WHERE key = 'last_disk_check'",
                (now,)
            )
            conn.commit()
    except Exception:
        pass  # Don't block if DB is locked

    return online


def get_cached_disk_status() -> dict:
    """Returns the last known disk status and check date from DB."""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            rows = conn.execute(
                "SELECT key, value FROM system_state WHERE key IN ('disk_online', 'last_disk_check')"
            ).fetchall()
            status = {row[0]: row[1] for row in rows}
            return {
                "online": status.get("disk_online") == "true",
                "last_check": status.get("last_disk_check", "Mai controllato"),
            }
    except Exception:
        return {"online": False, "last_check": "Errore lettura"}
