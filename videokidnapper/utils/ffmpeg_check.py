# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
import shutil
import subprocess
from pathlib import Path


def find_ffmpeg():
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        return Path(ffmpeg)
    bundled = Path(__file__).resolve().parent.parent.parent / "assets" / "ffmpeg" / "bin" / "ffmpeg.exe"
    if bundled.exists():
        return bundled
    return None


def find_ffprobe():
    ffprobe = shutil.which("ffprobe")
    if ffprobe:
        return Path(ffprobe)
    bundled = Path(__file__).resolve().parent.parent.parent / "assets" / "ffmpeg" / "bin" / "ffprobe.exe"
    if bundled.exists():
        return bundled
    return None


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
