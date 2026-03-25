import json
import os
import re
import subprocess
import tempfile
import threading
from pathlib import Path

from videokidnapper.config import PRESETS
from videokidnapper.utils.ffmpeg_check import find_ffmpeg, find_ffprobe

_ffmpeg = None
_ffprobe = None


def _get_ffmpeg():
    global _ffmpeg
    if _ffmpeg is None:
        _ffmpeg = str(find_ffmpeg())
    return _ffmpeg


def _get_ffprobe():
    global _ffprobe
    if _ffprobe is None:
        _ffprobe = str(find_ffprobe())
    return _ffprobe


def get_video_info(input_path):
    cmd = [
        _get_ffprobe(),
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        str(input_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    data = json.loads(result.stdout)
    video_stream = None
    for s in data.get("streams", []):
        if s.get("codec_type") == "video":
            video_stream = s
            break
    duration = float(data.get("format", {}).get("duration", 0))
    width = int(video_stream.get("width", 0)) if video_stream else 0
    height = int(video_stream.get("height", 0)) if video_stream else 0
    fps_str = video_stream.get("r_frame_rate", "30/1") if video_stream else "30/1"
    try:
        num, den = fps_str.split("/")
        fps = float(num) / float(den)
    except (ValueError, ZeroDivisionError):
        fps = 30.0
    return {
        "duration": duration,
        "width": width,
        "height": height,
        "fps": fps,
    }


def extract_frame(input_path, timestamp_seconds):
    from PIL import Image
    import io

    cmd = [
        _get_ffmpeg(),
        "-ss", str(timestamp_seconds),
        "-i", str(input_path),
        "-vframes", "1",
        "-f", "image2pipe",
        "-vcodec", "png",
        "-",
    ]
    result = subprocess.run(
        cmd, capture_output=True, timeout=10,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    if result.returncode != 0 or not result.stdout:
        return None
    return Image.open(io.BytesIO(result.stdout))


def _build_scale_filter(preset_name, input_width=None):
    preset = PRESETS[preset_name]
    target_width = preset["width"]
    if target_width is None or (input_width and input_width <= target_width):
        return None
    return f"scale={target_width}:-2"


def _parse_progress(process, duration, callback, cancel_event):
    pattern = re.compile(r"time=(\d+):(\d+):(\d+)\.(\d+)")
    for line in iter(process.stderr.readline, ""):
        if cancel_event and cancel_event.is_set():
            process.kill()
            return
        match = pattern.search(line)
        if match and callback and duration > 0:
            h, m, s, cs = int(match.group(1)), int(match.group(2)), int(match.group(3)), int(match.group(4))
            current = h * 3600 + m * 60 + s + cs / 100
            progress = min(current / duration, 1.0)
            callback(progress)


def _build_drawtext_filter(layer):
    from videokidnapper.ui.text_layers import _find_font_path
    text = layer["text"].replace("'", "\u2019").replace(":", "\\:")
    font_path = _find_font_path(layer.get("font", "Arial"))
    # FFmpeg on Windows needs forward slashes and escaped colons in paths
    font_path = font_path.replace("\\", "/").replace(":", "\\:")
    fontsize = layer.get("fontsize", 24)
    fontcolor = layer.get("fontcolor", "white")
    pos_expr = layer.get("position", "(w-tw)/2:h-th-20")
    x_expr, y_expr = pos_expr.split(":", 1)
    start_t = layer.get("start", 0)
    end_t = layer.get("end", 999999)

    parts = [
        f"drawtext=text='{text}'",
        f"fontfile='{font_path}'",
        f"fontsize={fontsize}",
        f"fontcolor={fontcolor}",
        f"x={x_expr}",
        f"y={y_expr}",
        f"enable='between(t,{start_t},{end_t})'",
    ]

    if layer.get("box"):
        boxcolor = layer.get("boxcolor", "black@0.6")
        boxborderw = layer.get("boxborderw", 8)
        parts.append("box=1")
        parts.append(f"boxcolor={boxcolor}")
        parts.append(f"boxborderw={boxborderw}")

    return ":".join(parts)


def _build_text_filters(text_layers):
    if not text_layers:
        return []
    return [_build_drawtext_filter(layer) for layer in text_layers]


def trim_to_video(input_path, start, end, preset_name, output_path,
                   text_layers=None, progress_callback=None, cancel_event=None):
    preset = PRESETS[preset_name]
    duration = end - start
    info = get_video_info(input_path)

    filters = []
    scale = _build_scale_filter(preset_name, info["width"])
    if scale:
        filters.append(scale)
    filters.extend(_build_text_filters(text_layers))

    cmd = [
        _get_ffmpeg(), "-y",
        "-ss", str(start),
        "-i", str(input_path),
        "-t", str(duration),
        "-r", str(preset["fps"]),
        "-c:v", "libx264",
        "-crf", str(preset["video_crf"]),
        "-preset", "medium",
        "-c:a", "aac",
        "-b:a", "128k",
    ]
    if filters:
        cmd += ["-vf", ",".join(filters)]
    cmd += ["-movflags", "+faststart", str(output_path)]

    process = subprocess.Popen(
        cmd, stderr=subprocess.PIPE, stdout=subprocess.DEVNULL, text=True,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    _parse_progress(process, duration, progress_callback, cancel_event)
    process.wait()
    return output_path if process.returncode == 0 else None


def trim_to_gif(input_path, start, end, preset_name, output_path,
                 text_layers=None, progress_callback=None, cancel_event=None):
    preset = PRESETS[preset_name]
    duration = end - start
    info = get_video_info(input_path)

    palette_path = Path(tempfile.mktemp(suffix=".png"))
    filters = [f"fps={preset['fps']}"]
    scale = _build_scale_filter(preset_name, info["width"])
    if scale:
        filters.append(scale)
    filters.extend(_build_text_filters(text_layers))
    filter_str = ",".join(filters)

    # Pass 1: generate palette
    cmd1 = [
        _get_ffmpeg(), "-y",
        "-ss", str(start),
        "-i", str(input_path),
        "-t", str(duration),
        "-vf", f"{filter_str},palettegen=max_colors={preset['gif_colors']}",
        str(palette_path),
    ]
    subprocess.run(
        cmd1, capture_output=True, timeout=120,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )

    if cancel_event and cancel_event.is_set():
        palette_path.unlink(missing_ok=True)
        return None

    if progress_callback:
        progress_callback(0.3)

    # Pass 2: encode GIF with palette
    cmd2 = [
        _get_ffmpeg(), "-y",
        "-ss", str(start),
        "-i", str(input_path),
        "-i", str(palette_path),
        "-t", str(duration),
        "-lavfi", f"{filter_str} [x]; [x][1:v] paletteuse=dither=bayer:bayer_scale=5",
        "-loop", "0",
        str(output_path),
    ]
    process = subprocess.Popen(
        cmd2, stderr=subprocess.PIPE, stdout=subprocess.DEVNULL, text=True,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )

    def gif_progress(p):
        if progress_callback:
            progress_callback(0.3 + p * 0.7)

    _parse_progress(process, duration, gif_progress, cancel_event)
    process.wait()
    palette_path.unlink(missing_ok=True)
    return output_path if process.returncode == 0 else None


def frames_to_video(frame_dir, fps, preset_name, output_path,
                     progress_callback=None, cancel_event=None):
    preset = PRESETS[preset_name]
    frame_dir = Path(frame_dir)
    frames = sorted(frame_dir.glob("frame_*.png"))
    if not frames:
        return None

    duration = len(frames) / fps

    filters = []
    scale = _build_scale_filter(preset_name)
    if scale:
        filters.append(scale)

    cmd = [
        _get_ffmpeg(), "-y",
        "-framerate", str(fps),
        "-i", str(frame_dir / "frame_%06d.png"),
        "-r", str(preset["fps"]),
        "-c:v", "libx264",
        "-crf", str(preset["video_crf"]),
        "-preset", "medium",
        "-pix_fmt", "yuv420p",
    ]
    if filters:
        cmd += ["-vf", ",".join(filters)]
    cmd += ["-movflags", "+faststart", str(output_path)]

    process = subprocess.Popen(
        cmd, stderr=subprocess.PIPE, stdout=subprocess.DEVNULL, text=True,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    _parse_progress(process, duration, progress_callback, cancel_event)
    process.wait()
    return output_path if process.returncode == 0 else None


def frames_to_gif(frame_dir, fps, preset_name, output_path,
                   progress_callback=None, cancel_event=None):
    preset = PRESETS[preset_name]
    frame_dir = Path(frame_dir)
    frames = sorted(frame_dir.glob("frame_*.png"))
    if not frames:
        return None

    duration = len(frames) / fps
    palette_path = Path(tempfile.mktemp(suffix=".png"))

    filters = [f"fps={preset['fps']}"]
    scale = _build_scale_filter(preset_name)
    if scale:
        filters.append(scale)
    filter_str = ",".join(filters)

    # Pass 1: palette
    cmd1 = [
        _get_ffmpeg(), "-y",
        "-framerate", str(fps),
        "-i", str(frame_dir / "frame_%06d.png"),
        "-vf", f"{filter_str},palettegen=max_colors={preset['gif_colors']}",
        str(palette_path),
    ]
    subprocess.run(
        cmd1, capture_output=True, timeout=120,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )

    if cancel_event and cancel_event.is_set():
        palette_path.unlink(missing_ok=True)
        return None

    if progress_callback:
        progress_callback(0.3)

    # Pass 2: encode
    cmd2 = [
        _get_ffmpeg(), "-y",
        "-framerate", str(fps),
        "-i", str(frame_dir / "frame_%06d.png"),
        "-i", str(palette_path),
        "-lavfi", f"{filter_str} [x]; [x][1:v] paletteuse=dither=bayer:bayer_scale=5",
        "-loop", "0",
        str(output_path),
    ]
    process = subprocess.Popen(
        cmd2, stderr=subprocess.PIPE, stdout=subprocess.DEVNULL, text=True,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )

    def gif_progress(p):
        if progress_callback:
            progress_callback(0.3 + p * 0.7)

    _parse_progress(process, duration, gif_progress, cancel_event)
    process.wait()
    palette_path.unlink(missing_ok=True)
    return output_path if process.returncode == 0 else None
