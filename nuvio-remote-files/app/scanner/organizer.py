"""
Media Auto-Organizer.

This module scans a 'downloads' directory for messy media files,
identifies them using regex and TMDB, and moves them into the structured
'movies' or 'series' directories with standardized naming.
"""

import os
import re
import shutil
from pathlib import Path

from core.config import (
    MOVIES_DIR_NAME,
    SERIES_DIR_NAME,
    DOWNLOADS_DIR_NAME,
)
from metadata.tmdb import lookup_movie, lookup_series

# Base paths
MEDIA_ROOT = Path("/media")
MOVIES_ROOT = MEDIA_ROOT / MOVIES_DIR_NAME
SERIES_ROOT = MEDIA_ROOT / SERIES_DIR_NAME
DOWNLOADS_ROOT = MEDIA_ROOT / DOWNLOADS_DIR_NAME

# Video extensions to process
VIDEO_EXTENSIONS = {".mkv", ".mp4", ".avi", ".mov", ".m4v", ".wmv"}

# Regex patterns
EPISODE_PATTERN = re.compile(r"S(?P<season>\d{1,2})E(?P<episode>\d{1,2})", re.IGNORECASE)
ALT_EPISODE_PATTERN = re.compile(r"(?P<season>\d{1,2})x(?P<episode>\d{1,2})", re.IGNORECASE)
YEAR_PATTERN = re.compile(r"(?P<year>19\d{2}|20\d{2})")
RESOLUTION_PATTERN = re.compile(r"(?P<res>2160p|1080p|720p|480p|576p|4K|2K|UHD|HD)", re.IGNORECASE)


def clean_name(name: str) -> str:
    """Remove dots, underscores and extra spaces from a name."""
    return name.replace(".", " ").replace("_", " ").strip()


def parse_filename(filename: str):
    """
    Parse a messy filename to extract title and metadata.
    Returns (is_series, title, year, season, episode, resolution)
    """
    stem = Path(filename).stem
    
    # Try to find resolution
    res_match = RESOLUTION_PATTERN.search(stem)
    resolution = res_match.group("res").lower() if res_match else None
    if resolution == "uhd": resolution = "2160p"
    if resolution == "hd": resolution = "1080p"
    if resolution == "4k": resolution = "2160p"

    # Try to find series pattern
    ep_match = EPISODE_PATTERN.search(stem) or ALT_EPISODE_PATTERN.search(stem)
    if ep_match:
        # It's a series
        season = int(ep_match.group("season"))
        episode = int(ep_match.group("episode"))
        
        # Extract title: look before AND after the match
        title_before = stem[:ep_match.start()].strip(" .-_")
        title_after = stem[ep_match.end():].strip(" .-_")
        
        if title_before:
            title = clean_name(title_before)
        else:
            # If nothing before, use everything after up to the resolution or year
            # We can simplify by taking title_after and cleaning it from common tags
            potential_title = title_after
            
            # Remove resolution from title if present
            res_match_in_after = RESOLUTION_PATTERN.search(potential_title)
            if res_match_in_after:
                potential_title = potential_title[:res_match_in_after.start()].strip(" .-_")
            
            # Remove year from title if present
            year_match_in_after = YEAR_PATTERN.search(potential_title)
            if year_match_in_after:
                potential_title = potential_title[:year_match_in_after.start()].strip(" .-_")
            
            title = clean_name(potential_title)
        
        return True, title, None, season, episode, resolution

    # Try to find year pattern (likely a movie)
    year_match = YEAR_PATTERN.search(stem)
    if year_match:
        year = int(year_match.group("year"))
        title_raw = stem[:year_match.start()].strip(" .-_")
        title = clean_name(title_raw)
        return False, title, year, None, None, resolution

    # Fallback: assume movie, use everything before resolution or the whole name
    title_raw = stem
    if res_match:
        title_raw = stem[:res_match.start()].strip(" .-_")
    
    return False, clean_name(title_raw), None, None, None, resolution


def organize_downloads():
    """
    Recursively scan DOWNLOADS_ROOT, identify files, and move them.
    """
    if not DOWNLOADS_ROOT.exists():
        print(f"[ORGANIZE] Downloads directory not found: {DOWNLOADS_ROOT}")
        return

    # Create destination roots if they don't exist
    MOVIES_ROOT.mkdir(parents=True, exist_ok=True)
    SERIES_ROOT.mkdir(parents=True, exist_ok=True)

    print(f"[ORGANIZE] Starting organization in {DOWNLOADS_ROOT}...")

    # Iterate recursively over all files
    for path in DOWNLOADS_ROOT.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in VIDEO_EXTENSIONS:
            continue

        print(f"[ORGANIZE] Processing: {path.name}")
        
        is_series, title, year, season, episode, resolution = parse_filename(path.name)
        
        if is_series:
            # Series logic
            meta = lookup_series(title)
            if not meta:
                print(f"[ORGANIZE] [SKIP] Series not found on TMDB: {title}")
                continue
            
            clean_title = meta["title"]
            season_dir = SERIES_ROOT / clean_title / f"Season {season:02d}"
            season_dir.mkdir(parents=True, exist_ok=True)
            
            # Format: SXXEXX Title [1080p].ext
            # We don't have the episode title easily here without another API call,
            # but we can try to get it if we want. For now, let's stick to the requested format.
            res_tag = f" [{resolution}]" if resolution else ""
            new_filename = f"S{season:02d}E{episode:02d} {clean_title}{res_tag}{path.suffix}"
            dest_path = season_dir / new_filename
            
            try:
                print(f"[ORGANIZE] Moving Series: {path.name} -> {dest_path}")
                shutil.move(str(path), str(dest_path))
            except Exception as e:
                print(f"[ORGANIZE] [ERROR] Failed to move {path.name}: {e}")

        else:
            # Movie logic
            meta = lookup_movie(title, year)
            if not meta:
                print(f"[ORGANIZE] [SKIP] Movie not found on TMDB: {title} ({year})")
                continue
            
            clean_title = meta["title"]
            clean_year = meta["year"]
            res_tag = f" [{resolution}]" if resolution else ""
            
            # Format: Movie Title (YYYY) [1080p].ext
            new_filename = f"{clean_title} ({clean_year}){res_tag}{path.suffix}"
            dest_path = MOVIES_ROOT / new_filename
            
            try:
                print(f"[ORGANIZE] Moving Movie: {path.name} -> {dest_path}")
                shutil.move(str(path), str(dest_path))
            except Exception as e:
                print(f"[ORGANIZE] [ERROR] Failed to move {path.name}: {e}")

    # Cleanup: remove empty directories in DOWNLOADS_ROOT
    cleanup_empty_dirs(DOWNLOADS_ROOT)
    print("[ORGANIZE] Organization complete.")


def move_file(file_path: Path, is_series: bool, title: str, year: int = None, season: int = None, episode: int = None, resolution: str = None):
    """Move a specific file to its destination based on provided metadata."""
    if is_series:
        meta = lookup_series(title)
        if not meta:
            return False, f"Series not found: {title}"
        
        clean_title = meta["title"]
        season_dir = SERIES_ROOT / clean_title / f"Season {season:02d}"
        season_dir.mkdir(parents=True, exist_ok=True)
        
        res_tag = f" [{resolution}]" if resolution else ""
        new_filename = f"S{season:02d}E{episode:02d} {clean_title}{res_tag}{file_path.suffix}"
        dest_path = season_dir / new_filename
    else:
        meta = lookup_movie(title, year)
        if not meta:
            return False, f"Movie not found: {title} ({year})"
        
        clean_title = meta["title"]
        clean_year = meta["year"]
        res_tag = f" [{resolution}]" if resolution else ""
        new_filename = f"{clean_title} ({clean_year}){res_tag}{file_path.suffix}"
        dest_path = MOVIES_ROOT / new_filename

    try:
        # Create destination root if it doesn't exist
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        
        print(f"[ORGANIZE] Manually Moving: {file_path.name} -> {dest_path}")
        shutil.move(str(file_path), str(dest_path))
        return True, str(dest_path)
    except Exception as e:
        print(f"[ORGANIZE] [ERROR] Failed to move {file_path.name}: {e}")
        return False, str(e)


def cleanup_empty_dirs(path: Path):
    """Remove empty directories recursively."""
    for d in os.listdir(path):
        sub_path = path / d
        if sub_path.is_dir():
            cleanup_empty_dirs(sub_path)
            if not os.listdir(sub_path):
                print(f"[ORGANIZE] Removing empty directory: {sub_path}")
                sub_path.rmdir()
