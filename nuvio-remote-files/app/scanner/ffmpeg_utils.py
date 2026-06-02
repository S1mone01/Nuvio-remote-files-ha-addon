import json
import subprocess
import os
from pathlib import Path
from core.config import MOVIES_DIR_NAME, SERIES_DIR_NAME

# Global state for progress tracking
FILTERING_STATUS = {
    "is_running": False,
    "total": 0,
    "processed": 0,
    "current_file": ""
}

MEDIA_ROOT = Path("/media")
MOVIES_ROOT = MEDIA_ROOT / MOVIES_DIR_NAME
SERIES_ROOT = MEDIA_ROOT / SERIES_DIR_NAME

def process_mkv_tracks(input_path: Path) -> Path:
    """
    Filter MKV tracks to keep only Italian audio and subtitles.
    Returns the path to the processed file (which is the same as input_path).
    If processing fails or no Italian audio is found, returns the original path.
    """
    if input_path.suffix.lower() != ".mkv":
        return input_path

    if not input_path.exists():
        return input_path

    try:
        # 1. Analyze with ffprobe
        cmd = [
            "ffprobe", "-v", "error", "-show_entries",
            "stream=index,codec_type:stream_tags=language",
            "-of", "json", str(input_path)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        streams = data.get("streams", [])

        video_indices = []
        audio_indices = []
        subtitle_indices = []
        has_italian_audio = False
        other_languages_found = False

        for s in streams:
            idx = s.get("index")
            ctype = s.get("codec_type")
            lang = s.get("tags", {}).get("language", "").lower()

            if ctype == "video":
                video_indices.append(idx)
            elif ctype == "audio":
                if lang in ["ita", "it", "it-it", "ita-it"]:
                    audio_indices.append(idx)
                    has_italian_audio = True
                else:
                    other_languages_found = True
            elif ctype == "subtitle":
                if lang in ["ita", "it", "it-it", "ita-it"]:
                    subtitle_indices.append(idx)
                else:
                    other_languages_found = True

        # 2. Skip if no Italian audio found (per user request)
        if not has_italian_audio:
            print(f"[FFMPEG] No Italian audio found in {input_path.name}, skipping.")
            return input_path

        # 3. Skip if no other languages found (already filtered)
        if not other_languages_found:
            return input_path

        # 4. Filter with ffmpeg
        temp_output = input_path.with_suffix(".tmp.mkv")
        ffmpeg_cmd = ["ffmpeg", "-y", "-i", str(input_path)]
        
        # Build maps
        for idx in video_indices:
            ffmpeg_cmd.extend(["-map", f"0:{idx}"])
        for idx in audio_indices:
            ffmpeg_cmd.extend(["-map", f"0:{idx}"])
        for idx in subtitle_indices:
            ffmpeg_cmd.extend(["-map", f"0:{idx}"])
            
        ffmpeg_cmd.extend(["-c", "copy", str(temp_output)])
        
        print(f"[FFMPEG] Filtering {input_path.name}...")
        subprocess.run(ffmpeg_cmd, check=True, capture_output=True)
        
        # 5. Replace original safely
        if temp_output.exists() and temp_output.stat().st_size > 0:
            os.remove(input_path)
            temp_output.rename(input_path)
        
        return input_path

    except Exception as e:
        print(f"[FFMPEG] [ERROR] Failed to process {input_path.name}: {e}")
        # Cleanup temp file if it exists
        temp_output = input_path.with_suffix(".tmp.mkv")
        if temp_output.exists():
            try: os.remove(temp_output)
            except: pass
        return input_path

def filter_existing_library():
    """
    Background task to filter all MKV files in the library.
    """
    global FILTERING_STATUS
    
    if FILTERING_STATUS["is_running"]:
        return

    FILTERING_STATUS["is_running"] = True
    FILTERING_STATUS["processed"] = 0
    FILTERING_STATUS["total"] = 0
    FILTERING_STATUS["current_file"] = "Scansione libreria..."

    try:
        # Find all MKV files
        mkv_files = []
        for root in [MOVIES_ROOT, SERIES_ROOT]:
            if root.exists():
                for path in root.rglob("*.mkv"):
                    mkv_files.append(path)
        
        FILTERING_STATUS["total"] = len(mkv_files)
        
        for path in mkv_files:
            FILTERING_STATUS["current_file"] = path.name
            process_mkv_tracks(path)
            FILTERING_STATUS["processed"] += 1
            
    except Exception as e:
        print(f"[FFMPEG] [ERROR] Library filtering failed: {e}")
    finally:
        FILTERING_STATUS["is_running"] = False
        FILTERING_STATUS["current_file"] = ""
