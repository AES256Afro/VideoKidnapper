import re


def seconds_to_hms(seconds):
    if seconds < 0:
        seconds = 0
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def hms_to_seconds(hms):
    match = re.match(r"(\d+):(\d+):(\d+)(?:\.(\d+))?", hms.strip())
    if not match:
        raise ValueError(f"Invalid time format: {hms}")
    h, m, s = int(match.group(1)), int(match.group(2)), int(match.group(3))
    ms = int(match.group(4).ljust(3, "0")[:3]) if match.group(4) else 0
    return h * 3600 + m * 60 + s + ms / 1000


def format_duration(seconds):
    if seconds < 60:
        return f"{seconds:.1f}s"
    m = int(seconds // 60)
    s = seconds % 60
    return f"{m}m {s:.0f}s"
