from datetime import datetime
from pathlib import Path
from snapit.config import DOWNLOADS_DIR


def generate_export_path(mode, extension):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = f"SnapIt_{mode}_{timestamp}"
    ext = extension.lower().lstrip(".")
    output = DOWNLOADS_DIR / f"{base_name}.{ext}"
    counter = 1
    while output.exists():
        output = DOWNLOADS_DIR / f"{base_name}_{counter}.{ext}"
        counter += 1
    return output
