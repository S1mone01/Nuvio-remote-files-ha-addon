import re

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
    "AAC", "AC3", "Dolby Digital", "E-AC3", "DTS", "DTS-HD MA", "Dolby TrueHD", "Dolby Atmos",
    # Common Tags
    "MULTISUB", "MULTI", "DUBBED", "5\.1", "7\.1"
]

TAGS_PATTERN = re.compile(r"\b(" + "|".join(TAGS_LIST) + r")\b", re.IGNORECASE)

def clean_name(name: str) -> str:
    """Remove dots, underscores and extra spaces from a name."""
    return name.replace(".", " ").replace("_", " ").strip(" .-_()[]{}")

def extract_tags(filename: str) -> str | None:
    """
    Extract all matching tags from a filename and return them as a space-separated string.
    """
    found_tags = []
    # Using finditer to preserve order and avoid duplicates
    for match in TAGS_PATTERN.finditer(filename):
        tag = match.group(0).upper()
        if tag not in found_tags:
            found_tags.append(tag)
    
    return " ".join(found_tags) if found_tags else None
