import json
import os
import subprocess
import threading
import urllib.request
import urllib.parse
import urllib.error

from videokidnapper.config import TEMP_DIR

API_BASE = "https://koolaidgospel.com"
EXTRACT_URL = f"{API_BASE}/api/extract"
PROXY_URL = f"{API_BASE}/api/proxy"


def _ensure_temp_dir():
    TEMP_DIR.mkdir(parents=True, exist_ok=True)


def extract_video(url):
    data = json.dumps({"videoUrl": url}).encode("utf-8")
    req = urllib.request.Request(
        EXTRACT_URL,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Origin": "https://koolaidgospel.com",
            "Referer": "https://koolaidgospel.com/",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            return result
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return {"error": f"API error {e.code}: {body[:200]}"}
    except Exception as e:
        return {"error": str(e)}


def _get_proxy_url(video_url):
    encoded = urllib.parse.quote(video_url, safe="")
    return f"{PROXY_URL}?url={encoded}"


def _pick_best_variant(result):
    variants = result.get("variants", [])
    if variants:
        # Sort by bitrate descending, pick highest quality
        sorted_v = sorted(variants, key=lambda v: v.get("bitrate", 0), reverse=True)
        return sorted_v[0].get("url", result.get("video_url", ""))
    return result.get("video_url", "")


def get_download_info(result):
    platform = result.get("platform", "unknown")
    title = result.get("title", "Untitled")
    video_url = _pick_best_variant(result)
    audio_url = result.get("audio_url")
    thumbnail = result.get("thumbnail")

    variants = result.get("variants", [])
    quality_options = []
    if variants:
        for v in variants:
            label = v.get("quality", v.get("content_type", "unknown"))
            bitrate = v.get("bitrate", 0)
            if bitrate:
                label = f"{bitrate // 1000}kbps"
            quality_options.append({"label": label, "url": v.get("url", "")})

    return {
        "platform": platform,
        "title": title,
        "video_url": video_url,
        "audio_url": audio_url,
        "thumbnail": thumbnail,
        "quality_options": quality_options,
    }


def download_extracted_video(video_url, audio_url=None,
                              progress_callback=None, cancel_event=None):
    _ensure_temp_dir()
    cancel_event = cancel_event or threading.Event()

    # Use proxy URL
    proxy_video = _get_proxy_url(video_url)
    video_path = os.path.join(str(TEMP_DIR), "koolaid_video.mp4")

    try:
        _download_file(proxy_video, video_path, progress_callback, cancel_event, label="video")
    except Exception as e:
        return {"error": f"Video download failed: {e}"}

    if cancel_event.is_set():
        return {"error": "cancelled"}

    # If Reddit audio track exists, download and mux
    if audio_url:
        if progress_callback:
            progress_callback(0.7, "Downloading audio track...")

        proxy_audio = _get_proxy_url(audio_url)
        audio_path = os.path.join(str(TEMP_DIR), "koolaid_audio.mp4")

        try:
            _download_file(proxy_audio, audio_path, None, cancel_event, label="audio")
        except Exception:
            # Audio might not exist for all Reddit videos, continue without
            audio_path = None

        if audio_path and os.path.exists(audio_path) and os.path.getsize(audio_path) > 0:
            if progress_callback:
                progress_callback(0.85, "Muxing audio+video...")

            muxed_path = os.path.join(str(TEMP_DIR), "koolaid_muxed.mp4")
            try:
                _mux_audio_video(video_path, audio_path, muxed_path)
                video_path = muxed_path
            except Exception:
                pass  # Fall back to video-only

    if progress_callback:
        progress_callback(1.0, "Download complete")

    return {"path": video_path}


def _download_file(url, output_path, progress_callback, cancel_event, label=""):
    req = urllib.request.Request(
        url,
        headers={
            "Origin": "https://koolaidgospel.com",
            "Referer": "https://koolaidgospel.com/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) VideoKidnapper/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        total = int(resp.headers.get("Content-Length", 0))
        downloaded = 0
        chunk_size = 65536

        with open(output_path, "wb") as f:
            while True:
                if cancel_event and cancel_event.is_set():
                    raise Exception("cancelled")
                chunk = resp.read(chunk_size)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                if progress_callback and total > 0:
                    progress_callback(
                        downloaded / total * 0.65,
                        f"Downloading {label}... {downloaded // (1024*1024)}MB / {total // (1024*1024)}MB",
                    )


def _mux_audio_video(video_path, audio_path, output_path):
    from videokidnapper.utils.ffmpeg_check import find_ffmpeg
    ffmpeg = str(find_ffmpeg())
    cmd = [
        ffmpeg, "-y",
        "-i", video_path,
        "-i", audio_path,
        "-c:v", "copy",
        "-c:a", "aac",
        "-shortest",
        output_path,
    ]
    subprocess.run(
        cmd, capture_output=True, timeout=60,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
