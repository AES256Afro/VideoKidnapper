# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
import os
import shutil
import subprocess
import sys
from pathlib import Path


def _bundled_candidates(binary_name):
    """Places a bundled ffmpeg/ffprobe may live, in priority order.

    - Next to the app executable when frozen (PyInstaller). This is how
      the MSIX package ships ffmpeg: PATH inside the MSIX container is
      unreliable (the activation broker does not rebuild it from the
      registry), so PATH-based discovery cannot be the only route.
    - The repo/_MEIPASS-relative ``assets/ffmpeg/bin`` dir — the
      historical location the Setup dialog installs into for source
      checkouts.
    """
    exe = f"{binary_name}.exe" if os.name == "nt" else binary_name
    roots = []
    if getattr(sys, "frozen", False):
        roots.append(Path(sys.executable).resolve().parent)
    roots.append(Path(__file__).resolve().parent.parent.parent)
    for root in roots:
        yield root / "assets" / "ffmpeg" / "bin" / exe
        yield root / exe


def _find_binary(binary_name):
    found = shutil.which(binary_name)
    if found:
        return Path(found)
    for candidate in _bundled_candidates(binary_name):
        if candidate.exists():
            return candidate
    return None


def find_ffmpeg():
    return _find_binary("ffmpeg")


def find_ffprobe():
    return _find_binary("ffprobe")


def check_ffmpeg():
    ffmpeg = find_ffmpeg()
    ffprobe = find_ffprobe()
    if ffmpeg and ffprobe:
        try:
            subprocess.run([str(ffmpeg), "-version"], capture_output=True, timeout=5)
            return str(ffmpeg), str(ffprobe)
        except Exception:
            pass
    return None, None
