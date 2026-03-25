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

THEME_COLOR = "#1a73e8"
