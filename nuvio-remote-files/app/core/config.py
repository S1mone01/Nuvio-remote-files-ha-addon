"""
Application configuration.

This module centralizes environment-based configuration for the
Stremio Remote Files addon, including database paths, media base URLs,
and access tokens.
"""

import os
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
    If MEDIA_DISK_NAME is not set, it defaults to True to avoid blocking.
    """
    if not MEDIA_DISK_NAME:
        return True

    disk_path = Path("/media") / MEDIA_DISK_NAME
    # A disk is considered online if its mount directory exists and is not empty
    try:
        return disk_path.exists() and disk_path.is_dir() and any(disk_path.iterdir())
    except (PermissionError, OSError):
        return False
