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

SUPPORTED_PLATFORMS = {
    "YouTube":   [r"(?:www\.|m\.|music\.)?youtube\.com/", r"youtu\.be/"],
    "Instagram": [r"(?:www\.)?instagram\.com/"],
    "Bluesky":   [r"(?:www\.)?bsky\.app/", r"(?:www\.)?bsky\.social/"],
    "Twitter/X": [r"(?:www\.|mobile\.)?twitter\.com/", r"(?:www\.|mobile\.)?x\.com/"],
    "Reddit":    [r"(?:www\.|old\.|new\.|np\.)?reddit\.com/", r"redd\.it/", r"v\.redd\.it/"],
    "Facebook":  [r"(?:www\.|m\.|web\.)?facebook\.com/", r"fb\.watch/", r"(?:www\.)?fb\.com/"],
}

APP_NAME = "VideoKidnapper"
# Version is owned by `videokidnapper/__init__.py` so pyproject.toml
# (dynamic version) and the runtime agree. Do not hard-code it here.
from videokidnapper import __version__  # noqa: E402
APP_VERSION = __version__
WINDOW_SIZE = "1000x700"
MIN_WINDOW_SIZE = (680, 480)

TEMP_DIR = Path.home() / ".videokidnapper_temp"

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
