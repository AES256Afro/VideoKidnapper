# SPDX-FileCopyrightText: 2026 AES256Afro <https://github.com/AES256Afro>
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
    """Parse a typed time into float seconds.

    Takes ``HH:MM:SS[.mmm]`` as the boxes show it, and the short forms
    people type: ``M:SS``, plain seconds, a comma for the decimal point.
    "1:30" used to be refused and quietly put back to the old time.

    Raises ``ValueError`` for anything else — callers (entry widgets)
    catch this to ignore typos.
    """
    match = re.fullmatch(r"(?:(?:(\d+):)?(\d+):)?(\d+)(?:[.,](\d*))?",
                         str(hms).strip())
    if not match:
        raise ValueError(f"Invalid time format: {hms}")
    h, m, s = (int(g) if g else 0 for g in match.group(1, 2, 3))
    ms = int(match.group(4).ljust(3, "0")[:3]) if match.group(4) else 0
    return h * 3600 + m * 60 + s + ms / 1000


def seconds_to_short(seconds: float) -> str:
    """Compact timecode for tight UI: ``0:07``, ``1:12``, ``1:02:03``.

    ``seconds_to_hms`` is the right format where precision matters (the
    trim readout, project files). It is far too wide for a chip in a
    horizontal row, where the point is to scan several at once.
    """
    if seconds < 0:
        seconds = 0
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def format_duration(seconds: float) -> str:
    """Short human label: ``12.3s`` under a minute, ``2m 15s`` otherwise."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    m = int(seconds // 60)
    s = seconds % 60
    return f"{m}m {s:.0f}s"
