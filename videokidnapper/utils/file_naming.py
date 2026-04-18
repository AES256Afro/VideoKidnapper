from datetime import datetime
from pathlib import Path

from videokidnapper.config import DOWNLOADS_DIR


def generate_export_path(mode, extension, base_dir=None):
    base_dir = Path(base_dir) if base_dir else DOWNLOADS_DIR
    base_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = f"VidKid_{mode}_{timestamp}"
    ext = extension.lower().lstrip(".")
    output = base_dir / f"{base_name}.{ext}"
    counter = 1
    while output.exists():
        output = base_dir / f"{base_name}_{counter}.{ext}"
        counter += 1
    return output
