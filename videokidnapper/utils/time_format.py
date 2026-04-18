# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Human-readable time conversion helpers.

Kept fully typed so hot callers (slider → timestamp → export path) get
checked by any future static-analysis pass without needing a stub.
"""
import re


def seconds_to_hms(seconds: float) -> str:
    """Format ``seconds`` as ``HH:MM:SS.mmm``."""
    if seconds < 0:
        seconds = 0
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def hms_to_seconds(hms: str) -> float:
    """Parse an ``HH:MM:SS[.mmm]`` string into float seconds.

    Raises ``ValueError`` for inputs that don't match the expected
    shape — callers (entry widgets) catch this to ignore typos.
    """
    match = re.match(r"(\d+):(\d+):(\d+)(?:\.(\d+))?", hms.strip())
    if not match:
        raise ValueError(f"Invalid time format: {hms}")
    h, m, s = int(match.group(1)), int(match.group(2)), int(match.group(3))
    ms = int(match.group(4).ljust(3, "0")[:3]) if match.group(4) else 0
    return h * 3600 + m * 60 + s + ms / 1000


def format_duration(seconds: float) -> str:
    """Short human label: ``12.3s`` under a minute, ``2m 15s`` otherwise."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    m = int(seconds // 60)
    s = seconds % 60
    return f"{m}m {s:.0f}s"
