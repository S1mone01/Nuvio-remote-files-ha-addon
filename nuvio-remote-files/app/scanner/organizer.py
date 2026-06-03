"""
Media Auto-Organizer.

This module scans a 'downloads' directory for messy media files,
identifies them using regex and TMDB, and moves them into the structured
'movies' or 'series' directories with standardized naming.
"""

import os
import re
import shutil
import logging
from pathlib import Path

from core.config import (
    MOVIES_DIR_NAME,
    SERIES_DIR_NAME,
    DOWNLOADS_DIR_NAME,
    FILTER_MKV_TRACKS,
)
from scanner.utils import extract_tags, TAGS_PATTERN, clean_name
from metadata.tmdb import lookup_movie, lookup_series, lookup_episode

# Base paths
MEDIA_ROOT = Path("/media")
MOVIES_ROOT = MEDIA_ROOT / MOVIES_DIR_NAME
SERIES_ROOT = MEDIA_ROOT / SERIES_DIR_NAME
DOWNLOADS_ROOT = MEDIA_ROOT / DOWNLOADS_DIR_NAME

# Video extensions to process
VIDEO_EXTENSIONS = {".mkv", ".mp4", ".avi", ".mov", ".m4v", ".wmv"}

def process_mkv_if_enabled(path: Path):
    """Filter MKV tracks if the option is enabled."""
    logging.info(f"[ORGANIZE] Checking MKV filter for {path.name} (Enabled: {FILTER_MKV_TRACKS})")
    if FILTER_MKV_TRACKS and path.suffix.lower() == ".mkv":
        try:
            logging.info(f"[ORGANIZE] Filtering tracks for {path.name}...")
            from scanner.ffmpeg_utils import process_mkv_tracks
            process_mkv_tracks(path)
            logging.info(f"[ORGANIZE] Filtering complete for {path.name}")
        except Exception as e:
            logging.error(f"[ORGANIZE] [ERROR] Failed to filter MKV {path.name}: {e}")
    elif not FILTER_MKV_TRACKS:
        logging.info(f"[ORGANIZE] MKV filter is DISABLED in configuration.")

def get_clean_stem(filename: str) -> tuple[str, str]:
    """
    Safely split filename into stem and extension by checking against known video extensions.
    This prevents messy filenames with dots (but no extension) from being split incorrectly.
    """
    lower_name = filename.lower()
    for ext in VIDEO_EXTENSIONS:
        if lower_name.endswith(ext):
            return filename[:-len(ext)], ext
    return filename, ""

# Regex patterns
EPISODE_PATTERN = re.compile(r"S(?P<season>\d{1,2})E(?P<episode>\d{1,2})", re.IGNORECASE)
ALT_EPISODE_PATTERN = re.compile(r"(?P<season>\d{1,2})x(?P<episode>\d{1,2})", re.IGNORECASE)
YEAR_PATTERN = re.compile(r"\(?(?P<year>19\d{2}|20\d{2})\)?")

# Language patterns for truncation
LANG_PATTERN = re.compile(r"\b(ITA|ENG|FRA|GER|ESP|SPA|DEU|ITA\.ENG|ITA-ENG)\b", re.IGNORECASE)

def parse_filename(filename: str):
    """
    Parse a messy filename to extract title and metadata.
    Returns (is_series, title, year, season, episode, tags_string)
    """
    stem, _ = get_clean_stem(filename)
    
    # Use centralized tag extraction
    tags_string = extract_tags(stem)

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
            potential_title = title_before
        else:
            potential_title = title_after
            
        # Truncate title at the first metadata or language tag
        first_meta_pos = len(potential_title)
        
        # Check for tags using centralized pattern
        for match in TAGS_PATTERN.finditer(potential_title):
            if match.start() < first_meta_pos:
                first_meta_pos = match.start()
        
        # Check for year
        year_match = YEAR_PATTERN.search(potential_title)
        if year_match and year_match.start() < first_meta_pos:
            first_meta_pos = year_match.start()
            
        # Check for language tags (extra safety for recognition)
        lang_match = LANG_PATTERN.search(potential_title)
        if lang_match and lang_match.start() < first_meta_pos:
            first_meta_pos = lang_match.start()
            
        title = clean_name(potential_title[:first_meta_pos])
        
        return True, title, None, season, episode, tags_string

    # Try to find year pattern (likely a movie)
    year_match = YEAR_PATTERN.search(stem)
    if year_match:
        year = int(year_match.group("year"))
        title_raw = stem[:year_match.start()].strip(" .-_")
        
        # Truncate title_raw at first tag or language
        first_meta_pos = len(title_raw)
        for match in TAGS_PATTERN.finditer(title_raw):
            if match.start() < first_meta_pos:
                first_meta_pos = match.start()
        
        lang_match = LANG_PATTERN.search(title_raw)
        if lang_match and lang_match.start() < first_meta_pos:
            first_meta_pos = lang_match.start()
            
        title = clean_name(title_raw[:first_meta_pos])
        return False, title, year, None, None, tags_string

    # Fallback: assume movie
    title_raw = stem
    first_meta_pos = len(stem)
    for match in TAGS_PATTERN.finditer(stem):
        if match.start() < first_meta_pos:
            first_meta_pos = match.start()
    
    lang_match = LANG_PATTERN.search(stem)
    if lang_match and lang_match.start() < first_meta_pos:
        first_meta_pos = lang_match.start()
    
    title = clean_name(stem[:first_meta_pos])
    
    return False, title, None, None, None, tags_string


def organize_downloads():
    """
    Recursively scan DOWNLOADS_ROOT, identify files, and move them.
    """
    if not DOWNLOADS_ROOT.exists():
        logging.warning(f"[ORGANIZE] Downloads directory not found: {DOWNLOADS_ROOT}")
        return

    # Create destination roots if they don't exist
    MOVIES_ROOT.mkdir(parents=True, exist_ok=True)
    SERIES_ROOT.mkdir(parents=True, exist_ok=True)

    logging.info(f"[ORGANIZE] Starting organization in {DOWNLOADS_ROOT}...")

    # Iterate recursively over all files
    files_to_process = []
    for path in DOWNLOADS_ROOT.rglob("*"):
        if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS:
            files_to_process.append(path)
    
    _run_organization(files_to_process)


def organize_selected_downloads(relative_paths: list[str]):
    """
    Organize a specific list of files from DOWNLOADS_ROOT.
    """
    if not DOWNLOADS_ROOT.exists():
        return

    files_to_process = []
    for rel_path in relative_paths:
        path = DOWNLOADS_ROOT / rel_path
        if path.exists() and path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS:
            files_to_process.append(path)
    
    if files_to_process:
        _run_organization(files_to_process)


def _run_organization(files_to_process: list[Path]):
    """Internal helper to run the organization loop for a list of files."""
    from scanner.ffmpeg_utils import FILTERING_STATUS
    
    if not files_to_process:
        logging.info("[ORGANIZE] No files to process.")
        return

    FILTERING_STATUS["is_running"] = True
    FILTERING_STATUS["total"] = len(files_to_process)
    FILTERING_STATUS["processed"] = 0
    FILTERING_STATUS["last_error"] = None

    try:
        for path in files_to_process:
            FILTERING_STATUS["current_file"] = path.name
            logging.info(f"[ORGANIZE] Processing: {path.name}")
            
            process_mkv_if_enabled(path)
            
            is_series, title, year, season, episode, tags = parse_filename(path.name)
            
            if is_series:
                # Series logic - use smart lookup to handle extra words in title
                meta = smart_lookup_series(title)
                if not meta:
                    logging.warning(f"[ORGANIZE] [SKIP] Series not found on TMDB: {title}")
                    FILTERING_STATUS["processed"] += 1
                    continue

                clean_series_title = meta["title"]
                season_dir = SERIES_ROOT / clean_series_title / f"Season {season:02d}"
                season_dir.mkdir(parents=True, exist_ok=True)

                # Try to get episode title
                ep_meta = lookup_episode(meta.get("tmdb_id"), season, episode)
                # Use episode title if found, otherwise fallback to series title
                display_title = ep_meta["title"] if ep_meta and ep_meta.get("title") else clean_series_title

                tag_suffix = f" [{tags}]" if tags else ""

                new_filename = f"S{season:02d}E{episode:02d} {display_title}{tag_suffix}{path.suffix}"
                dest_path = season_dir / new_filename

                try:
                    logging.info(f"[ORGANIZE] Moving Series: {path.name} -> {dest_path}")
                    shutil.move(str(path), str(dest_path))
                except Exception as e:
                    logging.error(f"[ORGANIZE] [ERROR] Failed to move {path.name}: {e}")
            else:
                # Movie logic
                meta = lookup_movie(title, year)
                if not meta:
                    logging.warning(f"[ORGANIZE] [SKIP] Movie not found on TMDB: {title} ({year})")
                    FILTERING_STATUS["processed"] += 1
                    continue

                clean_title = meta["title"]
                clean_year = meta.get("year", year or "Unknown")
                tag_suffix = f" [{tags}]" if tags else ""

                new_filename = f"{clean_title} ({clean_year}){tag_suffix}{path.suffix}"
                dest_path = MOVIES_ROOT / new_filename

                try:
                    logging.info(f"[ORGANIZE] Moving Movie: {path.name} -> {dest_path}")
                    shutil.move(str(path), str(dest_path))
                except Exception as e:
                    logging.error(f"[ORGANIZE] [ERROR] Failed to move {path.name}: {e}")
            
            FILTERING_STATUS["processed"] += 1
    finally:
        FILTERING_STATUS["is_running"] = False
        FILTERING_STATUS["current_file"] = ""
        FILTERING_STATUS["current_step"] = ""

    # Cleanup: remove empty directories in DOWNLOADS_ROOT
    cleanup_empty_dirs(DOWNLOADS_ROOT)
    logging.info("[ORGANIZE] Organization complete.")


def smart_lookup_series(title: str):
    """
    Try to find a series on TMDB. If direct lookup fails, try shortening the title
    word by word from the right (to handle cases where episode title is included).
    """
    current_title = clean_name(title)
    logging.info(f"[ORGANIZE] Smart lookup start: '{current_title}'")
    
    meta = lookup_series(current_title)
    if meta:
        return meta
    
    # Fallback: try shortening word by word
    words = current_title.split()
    attempts = [current_title]
    
    while len(words) > 1:
        words.pop()
        shorter_title = clean_name(" ".join(words))
        if shorter_title in attempts:
            continue
            
        attempts.append(shorter_title)
        logging.info(f"[ORGANIZE] Fallback lookup attempt: '{shorter_title}'")
        meta = lookup_series(shorter_title)
        if meta:
            logging.info(f"[ORGANIZE] Found match for '{shorter_title}': {meta['title']}")
            return meta
    
    logging.warning(f"[ORGANIZE] Smart lookup failed for all attempts: {attempts}")
    return None


def move_file(file_path: Path, is_series: bool, title: str, year: int = None, season: int = None, episode: int = None, resolution: str = None):
    """Move a specific file to its destination based on provided metadata."""
    # Note: resolution here acts as the 'tags' string from the UI if manually edited
    if is_series:
        meta = smart_lookup_series(title)
        if not meta:
            return False, f"Serie non trovata su TMDB dopo vari tentativi. Prova a inserire solo il nome della serie (es. 'The Mentalist')."
        
        clean_series_title = meta.get("title", title)
        season_dir = SERIES_ROOT / clean_series_title / f"Season {season:02d}"
        season_dir.mkdir(parents=True, exist_ok=True)
        
        # Try to get episode title
        ep_meta = lookup_episode(meta.get("tmdb_id"), season, episode)
        display_title = ep_meta["title"] if ep_meta and ep_meta.get("title") else clean_series_title
        
        tag_suffix = f" [{resolution}]" if resolution else ""
        new_filename = f"S{season:02d}E{episode:02d} {display_title}{tag_suffix}{file_path.suffix}"
        dest_path = season_dir / new_filename
    else:
        meta = lookup_movie(title, year)
        if not meta:
            return False, f"Movie not found: {title} ({year})"
        
        clean_title = meta.get("title", title)
        clean_year = meta.get("year", year or "Unknown")
        tag_suffix = f" [{resolution}]" if resolution else ""
        new_filename = f"{clean_title} ({clean_year}){tag_suffix}{file_path.suffix}"
        dest_path = MOVIES_ROOT / new_filename

    try:
        # Create destination root if it doesn't exist
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        
        process_mkv_if_enabled(file_path)
        
        logging.info(f"[ORGANIZE] Manually Moving: {file_path.name} -> {dest_path}")
        shutil.move(str(file_path), str(dest_path))
        return True, str(dest_path)
    except Exception as e:
        logging.error(f"[ORGANIZE] [ERROR] Failed to move {file_path.name}: {e}")
        return False, str(e)


def cleanup_empty_dirs(path: Path):
    """Remove empty directories recursively."""
    for d in os.listdir(path):
        sub_path = path / d
        if sub_path.is_dir():
            cleanup_empty_dirs(sub_path)
            if not os.listdir(sub_path):
                logging.info(f"[ORGANIZE] Removing empty directory: {sub_path}")
                sub_path.rmdir()
