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
YEAR_PATTERN = re.compile(r"\(?(?P<year>19\d{2}|20\d{2})\)?")

# Comprehensive Tags Pattern (Languages removed as per user request)
TAGS_LIST = [
    # Sources
    "CAM", "HDCAM", "TS", "HDTS", "TC", "PPV", "TVRip", "SATRip", "DSRip", "DVRip", "HDTV", "PDTV",
    "WEBRip", "WEB-DL", "WEBCap", "DVDRip", "DVD5", "DVD9", "DVDRemux", "BDRip", "BRRip", "BluRay",
    "BDRemux", "UHD BluRay", "UHD Remux", "Remux", "WEB Remux",
    # Resolutions
    "480p", "576p", "720p", "1080p", "1440p", "2160p", "4320p", "4K", "8K", "UHD", "HD",
    # Codecs
    "XviD", "DivX", "x264", "H\.264", "AVC", "x265", "H\.265", "HEVC", "AV1",
    # HDR
    "HDR10", "HDR10\+", "Dolby Vision", "DV", "HLG",
    # Audio
    "AAC", "AC3", "Dolby Digital", "E-AC3", "DTS", "DTS-HD MA", "Dolby TrueHD", "Dolby Atmos"
]

# Create a single pattern to find all tags
TAGS_PATTERN = re.compile(r"\b(" + "|".join(TAGS_LIST) + r")\b", re.IGNORECASE)


def clean_name(name: str) -> str:
    """Remove dots, underscores and extra spaces from a name."""
    return name.replace(".", " ").replace("_", " ").strip(" .-_()[]{}")


def parse_filename(filename: str):
    """
    Parse a messy filename to extract title and metadata.
    Returns (is_series, title, year, season, episode, tags_string)
    """
    stem = Path(filename).stem
    
    # Find all tags
    found_tags = []
    # Using finditer to preserve order and avoid duplicates
    for match in TAGS_PATTERN.finditer(stem):
        tag = match.group(0).upper()
        if tag not in found_tags:
            found_tags.append(tag)
    
    tags_string = " ".join(found_tags) if found_tags else None

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
            potential_title = title_after
            # Find the position of the first tag or year to truncate the title
            first_meta_pos = len(potential_title)
            
            # Check for tags
            for match in TAGS_PATTERN.finditer(potential_title):
                if match.start() < first_meta_pos:
                    first_meta_pos = match.start()
            
            # Check for year
            year_match = YEAR_PATTERN.search(potential_title)
            if year_match and year_match.start() < first_meta_pos:
                first_meta_pos = year_match.start()
                
            title = clean_name(potential_title[:first_meta_pos])
        
        return True, title, None, season, episode, tags_string

    # Try to find year pattern (likely a movie)
    year_match = YEAR_PATTERN.search(stem)
    if year_match:
        year = int(year_match.group("year"))
        title_raw = stem[:year_match.start()].strip(" .-_")
        title = clean_name(title_raw)
        return False, title, year, None, None, tags_string

    # Fallback: assume movie
    title_raw = stem
    first_meta_pos = len(stem)
    for match in TAGS_PATTERN.finditer(stem):
        if match.start() < first_meta_pos:
            first_meta_pos = match.start()
    
    title = clean_name(stem[:first_meta_pos])
    
    return False, title, None, None, None, tags_string


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
        
        is_series, title, year, season, episode, tags = parse_filename(path.name)
        
        if is_series:
            # Series logic
            meta = lookup_series(title)
            if not meta:
                print(f"[ORGANIZE] [SKIP] Series not found on TMDB: {title}")
                continue
            
            clean_title = meta["title"]
            season_dir = SERIES_ROOT / clean_title / f"Season {season:02d}"
            season_dir.mkdir(parents=True, exist_ok=True)
            
            tag_suffix = f" [{tags}]" if tags else ""

            new_filename = f"S{season:02d}E{episode:02d} {clean_title}{tag_suffix}{path.suffix}"
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
            tag_suffix = f" [{tags}]" if tags else ""

            
            new_filename = f"{clean_title} ({clean_year}){tag_suffix}{path.suffix}"
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
    # Note: resolution here acts as the 'tags' string from the UI if manually edited
    if is_series:
        meta = lookup_series(title)
        if not meta:
            return False, f"Series not found: {title}"
        
        clean_title = meta["title"]
        season_dir = SERIES_ROOT / clean_title / f"Season {season:02d}"
        season_dir.mkdir(parents=True, exist_ok=True)
        
        tag_suffix = f" [{resolution}]" if resolution else ""
        new_filename = f"S{season:02d}E{episode:02d} {clean_title}{tag_suffix}{file_path.suffix}"
        dest_path = season_dir / new_filename
    else:
        meta = lookup_movie(title, year)
        if not meta:
            return False, f"Movie not found: {title} ({year})"
        
        clean_title = meta["title"]
        clean_year = meta["year"]
        tag_suffix = f" [{resolution}]" if resolution else ""
        new_filename = f"{clean_title} ({clean_year}){tag_suffix}{file_path.suffix}"
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
