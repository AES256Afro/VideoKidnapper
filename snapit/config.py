from pathlib import Path

PRESETS = {
    "Low": {"fps": 10, "width": 480, "gif_colors": 64, "video_crf": 28},
    "Medium": {"fps": 15, "width": 720, "gif_colors": 128, "video_crf": 23},
    "High": {"fps": 24, "width": 1080, "gif_colors": 256, "video_crf": 18},
    "Ultra": {"fps": 30, "width": None, "gif_colors": 256, "video_crf": 15},
}

DOWNLOADS_DIR = Path.home() / "Downloads"

SUPPORTED_VIDEO_EXTENSIONS = (".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".wmv")

EXPORT_FORMATS = ["GIF", "MP4"]

APP_NAME = "SnapIt"
APP_VERSION = "1.0.0"
WINDOW_SIZE = "1000x700"
MIN_WINDOW_SIZE = (800, 600)

TEMP_DIR = Path.home() / ".snapit_temp"

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
