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
    "current_step": "",
    "current_file_info": "", # New: track info (Kept/Removed)
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
        FILTERING_STATUS["current_file_info"] = ""
        
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
        subtitle_indices = []
        
        detected_audio = []
        kept_audio = []
        removed_audio = []

        # Keywords to identify Italian tracks
        ita_keywords = ["ita", "it", "italiano", "italian", "it-it", "ita-it"]

        for s in streams:
            idx = s.get("index")
            ctype = s.get("codec_type")
            tags = s.get("tags", {})
            lang = tags.get("language", "und").lower()
            title = tags.get("title", "")
            
            display_name = f"{lang}" + (f" ({title})" if title else "")

            if ctype == "video":
                video_indices.append(idx)
            elif ctype == "subtitle":
                subtitle_indices.append(idx)
            elif ctype == "audio":
                detected_audio.append(display_name)
                
                # Check for Italian
                is_italian = False
                if lang in ["ita", "it", "it-it", "ita-it"]:
                    is_italian = True
                
                if not is_italian:
                    for tag_val in tags.values():
                        val_lower = str(tag_val).lower()
                        if any(k in val_lower for k in ["italiano", "italian"]):
                            is_italian = True
                            break
                
                if is_italian:
                    audio_indices.append(idx)
                    kept_audio.append(display_name)
                else:
                    removed_audio.append(display_name)

        # Update info for UI
        info_parts = []
        if detected_audio:
            info_parts.append(f"Audio rilevati: {', '.join(detected_audio)}")
        if removed_audio:
            info_parts.append(f"Mantenuti: {', '.join(kept_audio)}")
            info_parts.append(f"Rimossi: {', '.join(removed_audio)}")
        else:
            info_parts.append("Solo tracce italiane rilevate, filtraggio non necessario.")
        
        FILTERING_STATUS["current_file_info"] = " | ".join(info_parts)

        # 2. Skip if no Italian audio found
        if not audio_indices:
            print(f"[FFMPEG] No Italian audio found in {input_path.name}, skipping to preserve existing tracks.")
            FILTERING_STATUS["current_file_info"] = "Nessun audio italiano trovato. File saltato per sicurezza."
            return input_path

        # 3. Skip if nothing to filter (only Italian audio already)
        if not removed_audio:
            return input_path

        # 4. Filter with ffmpeg
        FILTERING_STATUS["current_step"] = f"Filtraggio tracce (copia)..."
        temp_output = input_path.with_suffix(".tmp.mkv")
        
        # -nostdin: prevents hangs in background
        # -loglevel error: minimal output to avoid pipe issues
        ffmpeg_cmd = ["ffmpeg", "-nostdin", "-y", "-loglevel", "error", "-i", str(input_path)]
        
        for idx in video_indices:
            ffmpeg_cmd.extend(["-map", f"0:{idx}"])
        for idx in audio_indices:
            ffmpeg_cmd.extend(["-map", f"0:{idx}"])
        for idx in subtitle_indices:
            ffmpeg_cmd.extend(["-map", f"0:{idx}"])
            
        ffmpeg_cmd.extend(["-map_metadata", "0", "-map_chapters", "0", "-c", "copy"])
        
        # Force Italian audio as default and forced for better player compatibility
        ffmpeg_cmd.extend(["-disposition:a:0", "default+forced"])
        
        ffmpeg_cmd.append(str(temp_output))
        
        # Final safety check
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
    FILTERING_STATUS["current_file_info"] = ""
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
        FILTERING_STATUS["current_file_info"] = ""
