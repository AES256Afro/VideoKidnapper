# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
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


def get_preset(name: str) -> Optional[PlatformPreset]:
    """Return the preset dict for ``name``, or ``None`` for Custom / unknown.

    Unknown names resolve to ``None`` instead of raising so a stale
    settings value doesn't crash the app at startup.
    """
    return PLATFORM_PRESETS.get(name)
