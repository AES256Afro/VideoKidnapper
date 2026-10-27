# SPDX-FileCopyrightText: 2026 AES256Afro <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Platform export presets.

Each preset snaps three existing knobs at once — ``quality`` (PRESETS key),
``format`` (``"MP4"`` or ``"GIF"``), and ``aspect`` (an ASPECT_CHOICES key
from ``export_options``) — to values that fit a specific destination
(YouTube Shorts, Discord free tier, Slack, etc.). Users can still tweak
each knob afterward; the preset is a starting point, not a lock.

The ``None`` entry for ``"Custom"`` means "do not touch the current
selection" — selecting Custom leaves quality/format/aspect alone.
"""

from __future__ import annotations

from typing import Optional, TypedDict


class PlatformPreset(TypedDict):
    quality: str
    format: str
    aspect: str


PLATFORM_PRESETS: dict[str, Optional[PlatformPreset]] = {
    "Custom":             None,
    "YouTube 1080p":      {"quality": "High",   "format": "MP4", "aspect": "16:9"},
    "YouTube Shorts":     {"quality": "High",   "format": "MP4", "aspect": "9:16"},
    "Instagram Reel":     {"quality": "High",   "format": "MP4", "aspect": "9:16"},
    "Instagram Post":     {"quality": "High",   "format": "MP4", "aspect": "1:1"},
    "Instagram Story":    {"quality": "High",   "format": "MP4", "aspect": "9:16"},
    "TikTok":             {"quality": "High",   "format": "MP4", "aspect": "9:16"},
    "Twitter / X":        {"quality": "Medium", "format": "MP4", "aspect": "16:9"},
    "Bluesky":            {"quality": "Medium", "format": "MP4", "aspect": "16:9"},
    "Discord (8 MB)":     {"quality": "Low",    "format": "MP4", "aspect": "Source"},
    "Discord (25 MB)":    {"quality": "Medium", "format": "MP4", "aspect": "Source"},
    "Slack GIF":          {"quality": "Low",    "format": "GIF", "aspect": "Source"},
    "Web Embed":          {"quality": "Medium", "format": "MP4", "aspect": "16:9"},
}

PLATFORM_CHOICES: list[str] = list(PLATFORM_PRESETS.keys())

# Upload limits, in megabytes. A preset only sets the quality, so a long
# clip still came out bigger than Discord takes and the upload failed.
SIZE_LIMITS_MB: dict[str, int] = {
    "Discord (8 MB)": 8,
    "Discord (25 MB)": 25,
}


def size_warning(name: str, estimated_bytes: float) -> Optional[str]:
    """What to say when the estimate is over ``name``'s upload limit, else None."""
    limit = SIZE_LIMITS_MB.get(name)
    if not limit or not estimated_bytes:
        return None
    if estimated_bytes <= limit * 1024 * 1024:
        return None
    site = name.split(" (")[0]
    return (f"Probably over {site}'s {limit} MB limit. Choose a shorter part "
            f"or a lower quality.")


def get_preset(name: str) -> Optional[PlatformPreset]:
    """Return the preset dict for ``name``, or ``None`` for Custom / unknown.

    Unknown names resolve to ``None`` instead of raising so a stale
    settings value doesn't crash the app at startup.
    """
    return PLATFORM_PRESETS.get(name)
