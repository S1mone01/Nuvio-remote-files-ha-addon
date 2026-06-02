import json
import subprocess
from pathlib import Path

def get_mkv_tracks(file_path: Path):
    """
    Get all tracks from an MKV file using mkvmerge -J.
    """
    if not file_path.exists() or file_path.suffix.lower() != ".mkv":
        return []

    try:
        cmd = ["mkvmerge", "-J", str(file_path)]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        tracks = data.get("tracks", [])
        
        result_tracks = []
        for t in tracks:
            props = t.get("properties", {})
            result_tracks.append({
                "id": t.get("id"),
                "type": t.get("type"),
                "codec": t.get("codec"),
                "language": props.get("language", "und"),
                "title": props.get("track_name", ""),
                "is_default": props.get("default_track", False),
                "is_forced": props.get("forced_track", False),
                "is_enabled": props.get("enabled_track", True)
            })
        return result_tracks
    except Exception as e:
        print(f"[MKVUTILS] Error getting tracks for {file_path.name}: {e}")
        return []

def update_mkv_metadata(file_path: Path, track_updates: list):
    """
    Update MKV track metadata using mkvpropedit.
    track_updates: list of {id, type, language, title, is_default, is_forced, is_enabled}
    """
    if not file_path.exists() or file_path.suffix.lower() != ".mkv":
        return False, "File non trovato o non è un MKV"

    try:
        cmd = ["mkvpropedit", str(file_path)]
        
        for update in track_updates:
            t_id = update.get("id")
            t_type = update.get("type")
            
            # Selector for mkvpropedit (e.g., track:a1 for first audio, track:s1 for first subtitle)
            # Actually mkvpropedit can use global track IDs starting from 1 with --edit track:n
            # but mkvmerge -J IDs start from 0. 
            # mkvpropedit --edit track:ID+1 works if ID is from mkvmerge.
            # However, mkvpropedit also supports --edit track:n where n is the 1-based index 
            # of the track in the file.
            
            # The most reliable way is to use global track ID + 1 if mkvmerge ID is used.
            selector = f"track:{t_id + 1}"
            
            cmd.extend(["--edit", selector])
            
            if "language" in update:
                cmd.extend(["--set", f"language={update['language']}"])
            if "title" in update:
                cmd.extend(["--set", f"name={update['title']}"])
            if "is_default" in update:
                cmd.extend(["--set", f"flag-default={'1' if update['is_default'] else '0'}"])
            if "is_forced" in update:
                cmd.extend(["--set", f"flag-forced={'1' if update['is_forced'] else '0'}"])
            if "is_enabled" in update:
                cmd.extend(["--set", f"flag-enabled={'1' if update['is_enabled'] else '0'}"])

        subprocess.run(cmd, check=True, capture_output=True)
        return True, "Metadati aggiornati con successo"
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.decode().strip() or str(e)
        return False, f"Errore mkvpropedit: {error_msg}"
    except Exception as e:
        return False, str(e)
