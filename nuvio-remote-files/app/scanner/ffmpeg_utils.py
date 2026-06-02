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
    "current_file": "",
    "current_step": "", # New: Analisi, Filtraggio, etc.
    "last_error": None
}

MEDIA_ROOT = Path("/media")
MOVIES_ROOT = MEDIA_ROOT / MOVIES_DIR_NAME
SERIES_ROOT = MEDIA_ROOT / SERIES_DIR_NAME

def process_mkv_tracks(input_path: Path) -> Path:
    """
    Filter MKV tracks to keep only Italian audio, but keep ALL subtitles.
    """
    global FILTERING_STATUS
    
    if input_path.suffix.lower() != ".mkv":
        return input_path

    if not input_path.exists():
        return input_path

    try:
        # 1. Analyze with ffprobe
        FILTERING_STATUS["current_step"] = f"Analisi flussi..."
        cmd = [
            "ffprobe", "-v", "error", "-show_entries",
            "stream=index,codec_type,disposition:stream_tags",
            "-of", "json", str(input_path)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        streams = data.get("streams", [])

        video_indices = []
        audio_indices = []
        subtitle_indices = [] # We will keep ALL subtitles
        has_italian_audio = False
        other_audio_languages_found = False

        # Keywords to identify Italian tracks
        ita_keywords = ["ita", "it", "italiano", "italian", "it-it", "ita-it"]

        for s in streams:
            idx = s.get("index")
            ctype = s.get("codec_type")
            tags = s.get("tags", {})
            
            if ctype == "video":
                video_indices.append(idx)
            elif ctype == "subtitle":
                # KEEP ALL SUBTITLES as per user request
                subtitle_indices.append(idx)
            elif ctype == "audio":
                # Check for Italian in tags
                is_italian = False
                
                # Check 'language' tag first (standard)
                lang = tags.get("language", "").lower()
                if lang in ["ita", "it", "it-it", "ita-it"]:
                    is_italian = True
                
                # If not found in language, check title/name
                if not is_italian:
                    for tag_val in tags.values():
                        val_lower = str(tag_val).lower()
                        if any(k in val_lower for k in ["italiano", "italian"]):
                            is_italian = True
                            break
                
                if is_italian:
                    audio_indices.append(idx)
                    has_italian_audio = True
                else:
                    other_audio_languages_found = True

        # 2. Skip if no Italian audio found (Safety: don't leave file without audio)
        if not has_italian_audio:
            print(f"[FFMPEG] No Italian audio found in {input_path.name}, skipping to preserve existing tracks.")
            return input_path

        # 3. Skip if no other audio languages found (nothing to filter in audio)
        # and since we keep all subtitles, there's nothing else to filter.
        if not other_audio_languages_found:
            return input_path

        # 4. Filter with ffmpeg
        FILTERING_STATUS["current_step"] = f"Filtraggio tracce (copia)..."
        temp_output = input_path.with_suffix(".tmp.mkv")
        
        ffmpeg_cmd = ["ffmpeg", "-y", "-i", str(input_path)]
        
        # Map video
        for idx in video_indices:
            ffmpeg_cmd.extend(["-map", f"0:{idx}"])
        
        # Map ONLY Italian audio
        for idx in audio_indices:
            ffmpeg_cmd.extend(["-map", f"0:{idx}"])
            
        # Map ALL subtitles
        for idx in subtitle_indices:
            ffmpeg_cmd.extend(["-map", f"0:{idx}"])
            
        # Preserve all metadata, chapters, etc.
        ffmpeg_cmd.extend(["-map_metadata", "0", "-map_chapters", "0", "-c", "copy"])
        ffmpeg_cmd.append(str(temp_output))
        
        # Final safety check: must have at least one audio and one video
        if not audio_indices or not video_indices:
             return input_path

        subprocess.run(ffmpeg_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        
        # 5. Replace original safely
        FILTERING_STATUS["current_step"] = f"Salvataggio file..."
        if temp_output.exists() and temp_output.stat().st_size > 0:
            os.remove(input_path)
            temp_output.rename(input_path)
        
        return input_path

    except subprocess.CalledProcessError as e:
        err_msg = e.stderr.decode() if e.stderr else str(e)
        print(f"[FFMPEG] [ERROR] FFmpeg failed for {input_path.name}: {err_msg}")
        FILTERING_STATUS["last_error"] = f"Errore su {input_path.name}: {err_msg[:100]}..."
        # Cleanup temp file
        temp_output = input_path.with_suffix(".tmp.mkv")
        if temp_output.exists():
            try: os.remove(temp_output)
            except: pass
        return input_path
    except Exception as e:
        print(f"[FFMPEG] [ERROR] Failed to process {input_path.name}: {e}")
        FILTERING_STATUS["last_error"] = f"Errore generico su {input_path.name}: {str(e)}"
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
    FILTERING_STATUS["current_file"] = ""
    FILTERING_STATUS["current_step"] = "Scansione libreria..."
    FILTERING_STATUS["last_error"] = None

    try:
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
        FILTERING_STATUS["last_error"] = f"Errore critico: {str(e)}"
    finally:
        FILTERING_STATUS["is_running"] = False
        FILTERING_STATUS["current_file"] = ""
        FILTERING_STATUS["current_step"] = "Completato"

