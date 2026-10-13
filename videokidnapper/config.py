# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
from typing import Dict, Optional, TypedDict


class Preset(TypedDict):
    """Single-preset shape used by ``PRESETS`` below.

    ``width`` is ``None`` for the "no downscale" preset (Ultra); every
    other value is a plain int. Annotated so mypy can narrow
    ``preset["width"]`` to ``Optional[int]`` at the call site instead
    of the opaque ``object`` it would otherwise infer from a bare dict.
    """
    fps: int
    width: Optional[int]
    gif_colors: int
    video_crf: int


PRESETS: Dict[str, Preset] = {
    "Low": {"fps": 10, "width": 480, "gif_colors": 64, "video_crf": 28},
    "Medium": {"fps": 15, "width": 720, "gif_colors": 128, "video_crf": 23},
    "High": {"fps": 24, "width": 1080, "gif_colors": 256, "video_crf": 18},
    "Ultra": {"fps": 30, "width": None, "gif_colors": 256, "video_crf": 15},
}

DOWNLOADS_DIR = Path.home() / "Downloads"

SUPPORTED_VIDEO_EXTENSIONS = (
    ".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".wmv",
    ".gif",  # ffmpeg reads GIFs as input; useful for re-trimming existing GIFs
    ".m4v", ".mpeg", ".mpg", ".ts", ".mts", ".3gp",
)

EXPORT_FORMATS = ["GIF", "MP4"]

# Each platform's domains. A link belongs to a platform when its host is
# one of these or a subdomain of one (www., m., music., old., v., ...);
# see downloader.detect_platform.
SUPPORTED_PLATFORMS = {
    "YouTube":   ["youtube.com", "youtu.be", "youtube-nocookie.com"],
    "Instagram": ["instagram.com"],
    "Bluesky":   ["bsky.app", "bsky.social"],
    "Twitter/X": ["twitter.com", "x.com"],
    "Reddit":    ["reddit.com", "redd.it"],
    "Facebook":  ["facebook.com", "fb.watch", "fb.com"],
}

APP_NAME = "VideoKidnapper"
# Version is owned by `videokidnapper/__init__.py` so pyproject.toml
# (dynamic version) and the runtime agree. Do not hard-code it here.
from videokidnapper import __version__  # noqa: E402
APP_VERSION = __version__
# The Studio layout (media · preview · inspector over a timeline) wants
# room; App shrinks this to fit smaller screens.
WINDOW_SIZE = "1440x900"
MIN_WINDOW_SIZE = (1024, 640)

# Scratch space: partial downloads and screen-recording frames. What is
# left here is cleared on exit (see downloader.cleanup_temp), so nothing
# a project might point at may stay here.
TEMP_DIR = Path.home() / ".videokidnapper_temp"

# Media the app makes for you and keeps: finished downloads, and images
# pasted from the clipboard as stickers. Projects point at these files,
# so the app never deletes anything here. It lives in Downloads, beside
# where exports go by default, because a downloaded video is the user's
# own file: they should be able to find it, keep it or delete it. An
# app-data folder would hide it, and an uninstall would take it along.
MEDIA_DIR = DOWNLOADS_DIR / "VideoKidnapper"

THEME_COLOR = "#1a73e8"

TEXT_STYLES = {
    "Subtitle": {
        "position": "bottom_center",
        "fontsize": 24,
        "fontcolor": "white",
        "box": True,
        "boxcolor": "black@0.6",
        "boxborderw": 8,
    },
    "Caption": {
        # The social-media caption look: white text, black outline, no box.
        "position": "bottom_center",
        "fontsize": 28,
        "fontcolor": "white",
        "box": False,
        "borderw": 2,
        "bordercolor": "black",
    },
    "Title": {
        "position": "center",
        "fontsize": 48,
        "fontcolor": "white",
        "box": False,
    },
    "Watermark": {
        "position": "bottom_right",
        "fontsize": 14,
        "fontcolor": "white@0.5",
        "box": False,
    },
    "Custom": {
        "position": "bottom_center",
        "fontsize": 24,
        "fontcolor": "white",
        "box": False,
    },
}

POSITION_MAP = {
    "Bottom Center": "(w-tw)/2:h-th-20",
    "Top Center": "(w-tw)/2:20",
    "Center": "(w-tw)/2:(h-th)/2",
    "Top Left": "20:20",
    "Top Right": "w-tw-20:20",
    "Bottom Left": "20:h-th-20",
    "Bottom Right": "w-tw-20:h-th-20",
}

TEXT_COLORS = {
    "White": "white",
    "Black": "black",
    "Red": "#FF0000",
    "Yellow": "#FFFF00",
    "Cyan": "#00FFFF",
    "Green": "#00FF00",
    "Orange": "#FF8800",
    "Pink": "#FF69B4",
}
