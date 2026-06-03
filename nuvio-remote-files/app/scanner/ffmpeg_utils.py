import json
import subprocess
import os
import shutil
import logging
from pathlib import Path
from core.config import MOVIES_DIR_NAME, SERIES_DIR_NAME

import threading

# Global semaphore to limit concurrent ffmpeg/mkvmerge processes
# This is crucial to prevent OOM on memory-constrained systems (e.g. Raspberry Pi)
PROCESS_SEMAPHORE = threading.Semaphore(1)

# Global state for progress tracking
FILTERING_STATUS = {
    "is_running": False,
    "total": 0,
    "processed": 0,
    "current_file": "",
    "current_step": "",
    "current_file_info": "",
    "last_error": None
}

MEDIA_ROOT = Path("/media")
MOVIES_ROOT = MEDIA_ROOT / MOVIES_DIR_NAME
SERIES_ROOT = MEDIA_ROOT / SERIES_DIR_NAME

def check_requirements():
    """Check if necessary tools are installed."""
    for tool in ["ffmpeg", "ffprobe"]:
        if not shutil.which(tool):
            return False, f"Strumento '{tool}' non trovato. Assicurati di aver ricostruito l'addon (Rebuild)."
    return True, None

def process_mkv_tracks(input_path: Path) -> Path:
    """
    Filter MKV tracks to keep only Italian audio using ffmpeg.
    Physically removes other audio tracks to recover space.
    """
    global FILTERING_STATUS
    
    if input_path.suffix.lower() != ".mkv":
        return input_path

    if not input_path.exists():
        return input_path

    # If this is called individually (not part of a batch library filter),
    # we need to manage the "is_running" state ourselves for the UI to show progress.
    managed_running_state = False
    if not FILTERING_STATUS["is_running"]:
        FILTERING_STATUS["is_running"] = True
        FILTERING_STATUS["total"] = 1
        FILTERING_STATUS["processed"] = 0
        FILTERING_STATUS["current_file"] = input_path.name
        FILTERING_STATUS["last_error"] = None
        managed_running_state = True

    try:
        with PROCESS_SEMAPHORE:
            # 1. Analyze with ffprobe
            FILTERING_STATUS["current_step"] = f"Analisi flussi..."
            FILTERING_STATUS["current_file_info"] = ""
            
            cmd_probe = [
                "ffprobe", "-v", "error", "-show_entries",
                "stream=index,codec_type,disposition:stream_tags",
                "-of", "json", str(input_path)
            ]
            result = subprocess.run(cmd_probe, capture_output=True, text=True, check=True)
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
                    # KEEP ALL SUBTITLES
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

            # 2. Skip if no Italian audio found (Safety)
            if not audio_indices:
                FILTERING_STATUS["current_file_info"] = "Nessun audio italiano trovato. Saltato per sicurezza."
                return input_path

            # 3. Skip if nothing to filter
            if not removed_audio:
                return input_path

            # 4. Filter with ffmpeg
            FILTERING_STATUS["current_step"] = f"Pulizia fisica (ffmpeg)..."
            temp_output = input_path.with_suffix(".tmp.mkv")
            
            # -nostdin: prevents hangs in background
            # -loglevel error: minimal output
            ffmpeg_cmd = ["ffmpeg", "-nostdin", "-y", "-loglevel", "error", "-i", str(input_path)]
            
            # Map video
            for idx in video_indices:
                ffmpeg_cmd.extend(["-map", f"0:{idx}"])
            # Map Italian audio
            for idx in audio_indices:
                ffmpeg_cmd.extend(["-map", f"0:{idx}"])
            # Map ALL subtitles
            for idx in subtitle_indices:
                ffmpeg_cmd.extend(["-map", f"0:{idx}"])
                
            # Copy streams and preserve all metadata/chapters
            # -c copy : Pure bitstream copy, 100% original quality
            ffmpeg_cmd.extend([
                "-c", "copy",
                "-map_metadata", "0",
                "-map_chapters", "0"
            ])
            
            # Force Italian audio as default and forced
            ffmpeg_cmd.extend(["-disposition:a:0", "default+forced"])
            
            ffmpeg_cmd.append(str(temp_output))
            
            # Run ffmpeg
            result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                error_msg = result.stderr.strip() or "Errore sconosciuto ffmpeg"
                raise Exception(error_msg)

            # 5. Replace original safely
            FILTERING_STATUS["current_step"] = f"Salvataggio file..."
            if temp_output.exists() and temp_output.stat().st_size > 0:
                old_size = input_path.stat().st_size
                new_size = temp_output.stat().st_size
                saved = (old_size - new_size) / (1024 * 1024)
                
                os.remove(input_path)
                temp_output.rename(input_path)
                FILTERING_STATUS["current_file_info"] = f"Completato! Recuperati {saved:.1f} MB"
            
            if managed_running_state:
                FILTERING_STATUS["processed"] = 1

            return input_path

    except Exception as e:
        logging.error(f"[FFMPEG] [ERROR] Failed to process {input_path.name}: {e}")
        FILTERING_STATUS["last_error"] = f"Errore su {input_path.name}: {str(e)[:150]}"
        temp_output = input_path.with_suffix(".tmp.mkv")
        if temp_output.exists():
            try: os.remove(temp_output)
            except: pass
        return input_path
    finally:
        if managed_running_state:
            # Short delay to let the UI see the completion if it was very fast
            # but since this is synchronous in a thread, we just reset it.
            FILTERING_STATUS["is_running"] = False
            FILTERING_STATUS["current_step"] = ""

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
    FILTERING_STATUS["current_step"] = "Verifica requisiti..."
    FILTERING_STATUS["current_file_info"] = ""
    FILTERING_STATUS["last_error"] = None

    try:
        ok, err = check_requirements()
        if not ok:
            FILTERING_STATUS["last_error"] = err
            return

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
        logging.error(f"[FFMPEG] Library filtering failed: {e}")
        FILTERING_STATUS["last_error"] = f"Errore critico: {str(e)}"
    finally:
        FILTERING_STATUS["is_running"] = False
        FILTERING_STATUS["current_file"] = ""
        FILTERING_STATUS["current_step"] = "Completato"
        FILTERING_STATUS["current_file_info"] = ""
