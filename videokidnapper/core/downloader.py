import os
import re
import threading

from videokidnapper.config import SUPPORTED_PLATFORMS, TEMP_DIR
from videokidnapper.utils.ffmpeg_check import find_ffmpeg


_DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def detect_platform(url):
    """Return the matching platform name from SUPPORTED_PLATFORMS, or None."""
    if not url:
        return None
    for name, patterns in SUPPORTED_PLATFORMS.items():
        for pat in patterns:
            if re.search(pat, url, re.IGNORECASE):
                return name
    return None


def _ensure_temp_dir():
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    return str(TEMP_DIR)


def _build_ydl_opts(url, ffmpeg_dir, progress_hook, cookies=None):
    """yt-dlp options tuned per platform.

    Default format `bv*+ba/best` is the yt-dlp recommended selector — it works
    across YouTube, Instagram, Bluesky, Twitter/X, and Reddit, unlike the
    mp4-only chain which fails on platforms that don't expose m4a audio.

    ``cookies`` can be one of:
      - a dict ``{"browser": "chrome"}`` / ``{"file": "/path/cookies.txt"}``
      - ``None`` to skip.
    """
    platform = detect_platform(url)

    opts = {
        "format": "bv*+ba/best",
        "outtmpl": os.path.join(str(TEMP_DIR), "%(title).80s.%(ext)s"),
        "merge_output_format": "mp4",
        "progress_hooks": [progress_hook],
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "restrictfilenames": True,
        "http_headers": {"User-Agent": _DEFAULT_UA},
        "retries": 3,
        "fragment_retries": 3,
    }
    if ffmpeg_dir:
        opts["ffmpeg_location"] = ffmpeg_dir

    if cookies:
        if cookies.get("file"):
            opts["cookiefile"] = cookies["file"]
        elif cookies.get("browser"):
            opts["cookiesfrombrowser"] = (cookies["browser"],)

    # Reddit hosts HLS fragments on v.redd.it; prefer mp4 container on merge.
    if platform == "Reddit":
        opts["format"] = "bv*+ba/b"
    # Twitter/X and Instagram often serve a single progressive mp4 already.
    elif platform in ("Twitter/X", "Instagram"):
        opts["format"] = "best[ext=mp4]/bv*+ba/best"
    # Bluesky videos are HLS; let yt-dlp pick the best variant.
    elif platform == "Bluesky":
        opts["format"] = "bv*+ba/best"

    return opts, platform


def download_video(url, progress_callback=None, cancel_event=None, cookies=None):
    import yt_dlp

    _ensure_temp_dir()
    result = {"path": None, "title": None, "platform": None, "error": None}
    cancel_event = cancel_event or threading.Event()

    def progress_hook(d):
        if cancel_event.is_set():
            raise Exception("Download cancelled")
        if d["status"] == "downloading" and progress_callback:
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            downloaded = d.get("downloaded_bytes", 0)
            if total > 0:
                progress_callback(
                    downloaded / total,
                    f"Downloading... {downloaded // (1024*1024)}MB / {total // (1024*1024)}MB",
                )
            else:
                progress_callback(0.5, f"Downloading... {downloaded // (1024*1024)}MB")
        elif d["status"] == "finished" and progress_callback:
            progress_callback(0.95, "Processing download...")

    ffmpeg_path = find_ffmpeg()
    ffmpeg_dir = str(ffmpeg_path.parent) if ffmpeg_path else None

    opts, platform = _build_ydl_opts(url, ffmpeg_dir, progress_hook, cookies=cookies)
    result["platform"] = platform

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            # Some extractors (Reddit galleries, Twitter threads) return a
            # playlist-like dict with `entries`; yt-dlp still downloads the
            # first video because `noplaylist=True`, so unwrap it here.
            if info.get("entries"):
                entries = [e for e in info["entries"] if e]
                if entries:
                    info = entries[0]
            result["title"] = info.get("title") or info.get("id") or "Unknown"
            if info.get("requested_downloads"):
                result["path"] = info["requested_downloads"][0]["filepath"]
            else:
                result["path"] = ydl.prepare_filename(info)
                base, _ = os.path.splitext(result["path"])
                mp4_path = base + ".mp4"
                if os.path.exists(mp4_path):
                    result["path"] = mp4_path
    except Exception as e:
        err_msg = re.sub(r"\x1b\[[0-9;]*m", "", str(e))
        if "cancelled" in err_msg.lower():
            result["error"] = "cancelled"
        else:
            result["error"] = _friendly_error(err_msg, platform)

    return result


def _friendly_error(msg, platform):
    """Attach platform-specific hints to common yt-dlp failures."""
    low = msg.lower()
    if "login" in low or "private" in low or "not available" in low or "unavailable" in low:
        if platform == "Instagram":
            return (
                "Instagram requires login for most videos. Export cookies from a "
                "logged-in browser and see yt-dlp's --cookies-from-browser docs. "
                f"(raw: {msg[:120]})"
            )
        if platform == "Twitter/X":
            return (
                "This X/Twitter post is private or age-restricted. A logged-in "
                f"cookies file may be required. (raw: {msg[:120]})"
            )
    if "unsupported url" in low:
        return (
            "URL not recognized by yt-dlp. Supported platforms: YouTube, "
            "Instagram, Bluesky, Twitter/X, Reddit."
        )
    return msg


def get_video_info_from_url(url):
    import yt_dlp

    opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "http_headers": {"User-Agent": _DEFAULT_UA},
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if info.get("entries"):
                entries = [e for e in info["entries"] if e]
                if entries:
                    info = entries[0]
            return {
                "title": info.get("title", "Unknown"),
                "duration": info.get("duration", 0),
                "uploader": info.get("uploader", "Unknown"),
                "thumbnail": info.get("thumbnail"),
                "platform": detect_platform(url),
            }
    except Exception as e:
        return {"error": str(e)}


def cleanup_temp():
    import shutil
    if TEMP_DIR.exists():
        shutil.rmtree(str(TEMP_DIR), ignore_errors=True)
