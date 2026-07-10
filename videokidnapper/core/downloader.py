# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
import os
import re
import threading

from videokidnapper.config import SUPPORTED_PLATFORMS, TEMP_DIR
from videokidnapper.utils.ffmpeg_check import find_ffmpeg


_DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# Shown when a download is attempted with no internet. Downloading is
# inherently online, so we say so plainly and point at the offline-capable
# half of the app instead of surfacing a cryptic DNS error. (Also satisfies
# Microsoft Store policy 10.1.2.10: graceful behaviour when offline.)
OFFLINE_MESSAGE = (
    "No internet connection. Connect to the internet to download videos. "
    "You can still open a local file to trim, caption, and export."
)


def has_internet(timeout=2.0):
    """Best-effort connectivity probe used to tell "the whole connection is
    down" (offline) apart from "this one link didn't resolve" after a
    DNS-style download failure, so each gets the right message.

    Opens a raw TCP socket to well-known public IPs (no DNS needed, so a
    genuinely offline machine fails fast with 'network unreachable'). Tries
    a couple of endpoints so one blocked port isn't a false negative. Only
    called on the failure path, never on a successful download.
    """
    import socket
    for host, port in (("1.1.1.1", 443), ("8.8.8.8", 53)):
        try:
            socket.create_connection((host, port), timeout=timeout).close()
            return True
        except OSError:
            continue
    return False


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
        # Resume partially-downloaded files instead of restarting — with
        # the outer retry loop in download_video, a dropped connection
        # at 90% picks up at 90%, not at zero.
        "continuedl": True,
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


# Error-text fragments that point at a transient network problem rather
# than a permanent failure (private video, unsupported URL, bad cookies).
# Lowercase substrings, matched against the stripped yt-dlp error text.
_TRANSIENT_ERROR_SIGNS = (
    "timed out",
    "timeout",
    "connection reset",
    "connection refused",
    "connection aborted",
    "temporary failure",
    "temporarily unavailable",
    "incomplete read",
    "incompleteread",
    "http error 429",
    "http error 500",
    "http error 502",
    "http error 503",
    "http error 504",
    "remote end closed",
    "ssl",
    "getaddrinfo failed",
    "network is unreachable",
)


def _is_transient_error(msg):
    """True when a download error is worth retrying."""
    low = str(msg or "").lower()
    return any(sign in low for sign in _TRANSIENT_ERROR_SIGNS)


# Error fragments that mean the machine can't reach the network at all
# (DNS can't resolve, no route) rather than a site-specific failure. These
# get the plain-English offline message, not a raw yt-dlp error dump.
_OFFLINE_ERROR_SIGNS = (
    "getaddrinfo failed",
    "failed to resolve",
    "name or service not known",
    "temporary failure in name resolution",
    "nodename nor servname",
    "network is unreachable",
    "no address associated with hostname",
)


def _is_offline_error(msg):
    low = str(msg or "").lower()
    return any(sign in low for sign in _OFFLINE_ERROR_SIGNS)


def _retry_delay(attempt):
    """Backoff schedule for download retries: 2s, 4s, 8s, capped at 8s."""
    return min(2 ** attempt, 8)


# Reddit serves image and GIF posts through a `reddit.com/media?url=<enc>`
# redirect that yt-dlp reports as an "Unsupported URL", but the true
# i.redd.it media URL is right there in the query param. We decode it and
# fetch it directly — Reddit GIF posts are exactly this app's use case.
_REDDIT_MEDIA_RE = re.compile(
    r"https?://(?:www\.)?reddit\.com/media\?url=([^\s'\"&]+)", re.IGNORECASE
)


def _reddit_media_url(err_msg):
    """Decode the real media URL from a Reddit ``/media?url=`` error, or None."""
    from urllib.parse import unquote
    m = _REDDIT_MEDIA_RE.search(err_msg or "")
    return unquote(m.group(1)) if m else None


def _download_direct_media(media_url, progress_callback=None, cancel_event=None):
    """Fetch a direct media file (a Reddit GIF/image redirect target) over
    plain HTTP with a browser User-Agent and save it to ``TEMP_DIR``.

    yt-dlp's default request gets bounced to the un-extractable /media
    HTML page; a browser User-Agent gets the real file instead. Only
    accepts GIF and video mime types — a static image post is reported
    back as an error rather than loaded into the editor as a dead frame.
    Returns the saved path; raises on a non-media response or read error.
    """
    import urllib.request
    from urllib.parse import urlparse

    _ensure_temp_dir()
    req = urllib.request.Request(media_url, headers={"User-Agent": _DEFAULT_UA})
    with urllib.request.urlopen(req, timeout=_PROBE_TIMEOUT_SECONDS) as resp:
        ctype = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if ctype != "image/gif" and not ctype.startswith("video/"):
            raise RuntimeError(
                f"this Reddit post is not a video or GIF (got {ctype or 'unknown type'})"
            )
        subtype = ctype.split("/", 1)[1] or "mp4"
        ext = ".gif" if ctype == "image/gif" else f".{subtype}"

        name = os.path.basename(urlparse(media_url).path) or "reddit_media"
        base, cur_ext = os.path.splitext(name)
        if cur_ext.lower() != ext:
            name = (base or "reddit_media") + ext
        out_path = os.path.join(str(TEMP_DIR), name)

        total = int(resp.headers.get("Content-Length") or 0)
        got = 0
        with open(out_path, "wb") as fh:
            while True:
                if cancel_event is not None and cancel_event.is_set():
                    raise Exception("Download cancelled")
                chunk = resp.read(65536)
                if not chunk:
                    break
                fh.write(chunk)
                got += len(chunk)
                if progress_callback and total:
                    progress_callback(
                        got / total,
                        f"Downloading... {got // (1024*1024)}MB / {total // (1024*1024)}MB",
                    )
    if progress_callback:
        progress_callback(0.95, "Processing download...")
    return out_path


def download_video(url, progress_callback=None, cancel_event=None, cookies=None,
                   max_attempts=3):
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

    # Outer retry loop for transient network failures. yt-dlp's own
    # ``retries`` handles per-request HTTP retries; this loop catches the
    # failures that surface as a raised error after those are exhausted
    # (mid-download connection drops, rate-limit bursts, flaky DNS).
    # ``continuedl`` makes each retry resume the partial file.
    last_error = None
    for attempt in range(1, max(1, int(max_attempts)) + 1):
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
            return result
        except Exception as e:
            err_msg = re.sub(r"\x1b\[[0-9;]*m", "", str(e))
            if "cancelled" in err_msg.lower():
                result["error"] = "cancelled"
                return result

            # Reddit image/GIF posts fail yt-dlp with a /media redirect that
            # names the real i.redd.it URL; fetch it directly instead of
            # retrying (retries can't help — yt-dlp has no extractor for it).
            media_url = _reddit_media_url(err_msg)
            if media_url:
                try:
                    path = _download_direct_media(
                        media_url, progress_callback, cancel_event)
                    result["path"] = path
                    result["title"] = os.path.splitext(os.path.basename(path))[0]
                    return result
                except Exception as fe:
                    fe_msg = str(fe)
                    if "cancelled" in fe_msg.lower():
                        result["error"] = "cancelled"
                        return result
                    result["error"] = _friendly_error(fe_msg, platform)
                    return result

            # DNS/route failure: don't retry into a cryptic error. Confirm
            # whether the whole connection is down (offline) or just this
            # host, and say so plainly — downloading needs a connection, but
            # opening/trimming/exporting a local file does not.
            if _is_offline_error(err_msg):
                if not has_internet():
                    result["error"] = OFFLINE_MESSAGE
                else:
                    result["error"] = (
                        "Couldn't reach that link. Check the URL and your "
                        "connection (VPN or DNS), then try again."
                    )
                return result

            last_error = err_msg
            if attempt < max_attempts and _is_transient_error(err_msg):
                if progress_callback:
                    progress_callback(
                        0.0,
                        f"Connection hiccup — retrying ({attempt + 1}/{max_attempts})...",
                    )
                # Event.wait doubles as an interruptible sleep: returns True
                # the moment the user cancels mid-backoff.
                if cancel_event.wait(_retry_delay(attempt)):
                    result["error"] = "cancelled"
                    return result
                continue
            break

    result["error"] = _friendly_error(last_error or "unknown error", platform)
    return result


def resolve_cookies(browser="", file=""):
    """Turn the persisted cookie settings into a ``download_video`` arg.

    A cookies file wins over a browser choice (the UI clears one when
    the other is picked, but a hand-edited settings file may carry
    both). Returns ``None`` when neither is configured.
    """
    if file:
        return {"file": file}
    if browser:
        return {"browser": browser}
    return None


# Error fragments that mean "yt-dlp could not get cookies out of the
# browser" rather than anything about the video itself. Chrome locks
# its cookie database while running, and Chrome 127+ on Windows
# additionally encrypts it (App-Bound Encryption) in a way yt-dlp
# cannot bypass even when the browser is closed.
_COOKIE_ERROR_SIGNS = (
    "could not copy",          # "Could not copy Chrome cookie database"
    "failed to decrypt",
    "app bound",
    "app-bound",
    "dpapi",
    "could not find",          # "could not find chrome cookies database"
)


def _is_cookie_error(msg):
    low = str(msg or "").lower()
    return "cookie" in low and any(sign in low for sign in _COOKIE_ERROR_SIGNS)


def _friendly_error(msg, platform):
    """Attach platform-specific hints to common yt-dlp failures."""
    low = msg.lower()
    # Lost the connection mid-download (preflight passed, then DNS/route
    # died): same plain-English message as the offline preflight.
    if _is_offline_error(msg):
        return OFFLINE_MESSAGE
    if _is_cookie_error(msg):
        # Front-loaded actions: the status bar truncates long errors, so
        # the fix has to fit in the first line.
        return (
            "Browser cookies unreadable. Close the browser fully and retry, "
            "switch Cookies to firefox, or pick 'Cookies file' and use a "
            "cookies.txt export. For public videos, '(no cookies)' works. "
            f"(raw: {msg[:120]})"
        )
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


_PROBE_TIMEOUT_SECONDS = 20


def get_video_info_from_url(url, timeout=_PROBE_TIMEOUT_SECONDS):
    """Probe a URL for video metadata without downloading.

    yt-dlp's ``extract_info`` has no native timeout knob, so we run it
    on a worker thread and impose a soft timeout from the outside. A
    stalled URL (dead CDN, rate-limiter eating the connection) would
    otherwise freeze the calling UI thread indefinitely — and in the
    batch-download panel, a single bad URL could stop the whole queue.

    Returns ``{"error": ...}`` on timeout or probe failure; otherwise
    a dict with ``title`` / ``duration`` / ``uploader`` / ``thumbnail``
    / ``platform``.
    """
    import yt_dlp

    opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "socket_timeout": max(5, int(timeout / 2)),
        "http_headers": {"User-Agent": _DEFAULT_UA},
    }

    result_box = {}

    def worker():
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if info.get("entries"):
                    entries = [e for e in info["entries"] if e]
                    if entries:
                        info = entries[0]
                result_box["ok"] = {
                    "title": info.get("title", "Unknown"),
                    "duration": info.get("duration", 0),
                    "uploader": info.get("uploader", "Unknown"),
                    "thumbnail": info.get("thumbnail"),
                    "platform": detect_platform(url),
                }
        except Exception as exc:
            result_box["error"] = str(exc)

    t = threading.Thread(target=worker, name="yt-dlp-probe", daemon=True)
    t.start()
    t.join(timeout)

    if t.is_alive():
        # yt-dlp is still running. Daemon thread will be reaped on
        # process exit; we can't kill it from the outside, so we just
        # stop waiting. The caller gets a clear timeout signal.
        return {"error": f"timed out after {timeout}s probing {url}"}
    if "error" in result_box:
        err = result_box["error"]
        return {"error": OFFLINE_MESSAGE if _is_offline_error(err) else err}
    return result_box.get("ok", {"error": "unknown probe failure"})


def cleanup_temp():
    import shutil
    if TEMP_DIR.exists():
        shutil.rmtree(str(TEMP_DIR), ignore_errors=True)
