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
    "current_file_info": "",
    "last_error": None
}

MEDIA_ROOT = Path("/media")
MOVIES_ROOT = MEDIA_ROOT / MOVIES_DIR_NAME
SERIES_ROOT = MEDIA_ROOT / SERIES_DIR_NAME

def process_mkv_tracks(input_path: Path) -> Path:
    """
    Physically remove non-Italian audio tracks to recover space.
    Uses mkvmerge for maximum speed and compatibility.
    """
    global FILTERING_STATUS
    
    if input_path.suffix.lower() != ".mkv":
        return input_path

    if not input_path.exists():
        return input_path

    try:
        # 1. Analyze with ffprobe to inform the user
        FILTERING_STATUS["current_step"] = f"Analisi flussi..."
        
        cmd_probe = [
            "ffprobe", "-v", "error", "-show_entries",
            "stream=index,codec_type,disposition:stream_tags",
            "-of", "json", str(input_path)
        ]
        result = subprocess.run(cmd_probe, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        streams = data.get("streams", [])

        has_italian_audio = False
        other_audio_found = False
        detected_audio = []
        first_ita_audio_id = None

        # Keywords to identify Italian tracks
        ita_keywords = ["ita", "it", "italiano", "italian", "it-it", "ita-it"]

        for s in streams:
            idx = s.get("index")
            ctype = s.get("codec_type")
            if ctype != "audio":
                continue
            
            tags = s.get("tags", {})
            lang = tags.get("language", "und").lower()
            title = tags.get("title", "")
            display_name = f"{lang}" + (f" ({title})" if title else "")
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
                has_italian_audio = True
                if first_ita_audio_id is None:
                    first_ita_audio_id = idx
            else:
                other_audio_found = True

        # 2. Skip logic
        if not has_italian_audio:
            FILTERING_STATUS["current_file_info"] = "Nessun audio italiano. File saltato per sicurezza."
            return input_path

        if not other_audio_found:
            FILTERING_STATUS["current_file_info"] = "Già solo audio italiano. Nessuna pulizia necessaria."
            return input_path

        # 3. Physical cleanup with mkvmerge
        FILTERING_STATUS["current_step"] = f"Pulizia fisica (Recupero spazio)..."
        FILTERING_STATUS["current_file_info"] = f"Audio rilevati: {', '.join(detected_audio)} | Rimozione tracce non ITA..."
        
        temp_output = input_path.with_suffix(".tmp.mkv")
        
        # mkvmerge command:
        # --audio-languages ita : keep only italian audio
        # --subtitle-languages all : keep all subtitles
        # --default-track-flag : ensure the first italian track is the default one
        cmd_merge = [
            "mkvmerge",
            "-o", str(temp_output),
            "--audio-languages", "ita,it",
            "--subtitle-languages", "all",
        ]
        
        if first_ita_audio_id is not None:
            cmd_merge.extend(["--default-track-flag", f"{first_ita_audio_id}:1"])
            
        cmd_merge.append(str(input_path))
        
        # Run mkvmerge
        result = subprocess.run(cmd_merge, capture_output=True, text=True)
        
        if result.returncode not in [0, 1]: # 0=success, 1=warnings (common in mkvmerge)
            raise Exception(f"mkvmerge failed: {result.stderr}")

        # 4. Replace original safely
        FILTERING_STATUS["current_step"] = f"Sostituzione file..."
        if temp_output.exists() and temp_output.stat().st_size > 0:
            # Check if we actually saved space or at least produced a valid file
            old_size = input_path.stat().st_size
            new_size = temp_output.stat().st_size
            saved = (old_size - new_size) / (1024 * 1024)
            
            os.remove(input_path)
            temp_output.rename(input_path)
            
            FILTERING_STATUS["current_file_info"] = f"Completato! Spazio recuperato: {saved:.1f} MB"
        
        return input_path

    except Exception as e:
        print(f"[MKVMERGE] [ERROR] Failed to process {input_path.name}: {e}")
        FILTERING_STATUS["last_error"] = f"Errore su {input_path.name}: {str(e)}"
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
        print(f"[MKVMERGE] [ERROR] Library filtering failed: {e}")
        FILTERING_STATUS["last_error"] = f"Errore critico: {str(e)}"
    finally:
        FILTERING_STATUS["is_running"] = False
        FILTERING_STATUS["current_file"] = ""
        FILTERING_STATUS["current_step"] = "Completato"
        FILTERING_STATUS["current_file_info"] = ""
