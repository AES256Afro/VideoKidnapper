import os
import re
import threading

from snapit.config import TEMP_DIR
from snapit.utils.ffmpeg_check import find_ffmpeg


def _ensure_temp_dir():
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    return str(TEMP_DIR)


def download_video(url, progress_callback=None, cancel_event=None):
    import yt_dlp

    _ensure_temp_dir()
    result = {"path": None, "title": None, "error": None}
    cancel_event = cancel_event or threading.Event()

    def progress_hook(d):
        if cancel_event.is_set():
            raise Exception("Download cancelled")
        if d["status"] == "downloading" and progress_callback:
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            downloaded = d.get("downloaded_bytes", 0)
            if total > 0:
                progress_callback(downloaded / total, f"Downloading... {downloaded // (1024*1024)}MB / {total // (1024*1024)}MB")
        elif d["status"] == "finished" and progress_callback:
            progress_callback(0.95, "Processing download...")

    ffmpeg_path = find_ffmpeg()
    ffmpeg_dir = str(ffmpeg_path.parent) if ffmpeg_path else None

    opts = {
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "outtmpl": os.path.join(str(TEMP_DIR), "%(title).80s.%(ext)s"),
        "merge_output_format": "mp4",
        "progress_hooks": [progress_hook],
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
    }
    if ffmpeg_dir:
        opts["ffmpeg_location"] = ffmpeg_dir

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            result["title"] = info.get("title", "Unknown")
            # Find the downloaded file
            if info.get("requested_downloads"):
                result["path"] = info["requested_downloads"][0]["filepath"]
            else:
                # Fallback: construct path from template
                result["path"] = ydl.prepare_filename(info)
                # yt-dlp may have merged to mp4
                base, _ = os.path.splitext(result["path"])
                mp4_path = base + ".mp4"
                if os.path.exists(mp4_path):
                    result["path"] = mp4_path
    except Exception as e:
        err_msg = re.sub(r"\x1b\[[0-9;]*m", "", str(e))  # strip ANSI codes
        if "cancelled" in err_msg.lower():
            result["error"] = "cancelled"
        else:
            result["error"] = err_msg

    return result


def get_video_info_from_url(url):
    import yt_dlp

    opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return {
                "title": info.get("title", "Unknown"),
                "duration": info.get("duration", 0),
                "uploader": info.get("uploader", "Unknown"),
                "thumbnail": info.get("thumbnail"),
            }
    except Exception as e:
        return {"error": str(e)}


def cleanup_temp():
    import shutil
    if TEMP_DIR.exists():
        shutil.rmtree(str(TEMP_DIR), ignore_errors=True)
