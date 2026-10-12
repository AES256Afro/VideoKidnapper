# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Real ffmpeg runs for the export bugs a unit test cannot see.

- A speed change made the clip the wrong length.
- Captions came out at the wrong moment for a range not starting at 0.
- A manual crop of an odd size made libx264 refuse the export.
- A failed export left a broken file behind.

Skipped when ffmpeg is not on PATH, like ``test_integration_ffmpeg``.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

from videokidnapper.core import ffmpeg_backend
from videokidnapper.core.ffmpeg import _internals
from videokidnapper.core.ffmpeg import encode


pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg / ffprobe not on PATH",
)

_OPTIONS = {"hw_encoder": "off", "mute": True}


@pytest.fixture(autouse=True)
def _fresh_binaries(monkeypatch):
    monkeypatch.setattr(_internals, "_ffmpeg", None)
    monkeypatch.setattr(_internals, "_ffprobe", None)
    monkeypatch.setattr(_internals, "_hw_encoders_cache", None)


@pytest.fixture(scope="module")
def source(tmp_path_factory):
    """6 s of black, 160x90, with a tone."""
    path = tmp_path_factory.mktemp("src") / "black.mp4"
    subprocess.run([
        "ffmpeg", "-v", "error", "-y",
        "-f", "lavfi", "-i", "color=c=black:s=160x90:d=6:r=24",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=6",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-shortest", str(path),
    ], check=True, capture_output=True, timeout=60)
    return path


def _duration(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True, timeout=30)
    return float(out.stdout.strip())


def _mean_luma(path, t):
    """Average brightness (0–255) of the frame at ``t`` seconds."""
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", str(path),
         "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
        capture_output=True, check=True, timeout=30).stdout
    assert raw, f"no frame at {t}s"
    return sum(raw) / len(raw)


@pytest.mark.parametrize("speed,expected", [(1.0, 2.0), (2.0, 1.0), (0.5, 4.0)])
def test_speed_sets_the_clip_length(source, tmp_path, speed, expected):
    out = tmp_path / "out.mp4"
    result = ffmpeg_backend.trim_to_video(
        str(source), 1.0, 3.0, "Low", str(out),
        options={**_OPTIONS, "speed": speed})
    assert result
    assert _duration(out) == pytest.approx(expected, abs=0.1)


def test_speed_sets_the_gif_length(source, tmp_path):
    out = tmp_path / "out.gif"
    assert ffmpeg_backend.trim_to_gif(
        str(source), 1.0, 3.0, "Low", str(out), options={"speed": 2.0})
    assert _duration(out) == pytest.approx(1.0, abs=0.15)


def test_caption_shows_at_its_source_time(source, tmp_path):
    # White box caption at 3–4 s on the source clock; export 2–6 s at 2x,
    # so on the output clock it is on screen from 0.5 to 1.0 s.
    out = tmp_path / "out.mp4"
    caption = {"text": "CAPTION", "fontsize": 40, "fontcolor": "white",
               "box": True, "boxcolor": "white", "boxborderw": 40,
               "position": "(w-tw)/2:(h-th)/2", "start": 3.0, "end": 4.0}
    assert ffmpeg_backend.trim_to_video(
        str(source), 2.0, 6.0, "Low", str(out), text_layers=[caption],
        options={**_OPTIONS, "speed": 2.0})
    assert _mean_luma(out, 0.25) < 20, "caption showed before its time"
    assert _mean_luma(out, 0.75) > 60, "caption missing while it should show"
    assert _mean_luma(out, 1.5) < 20, "caption stayed after its time"


def test_odd_sized_manual_crop_exports(source, tmp_path):
    out = tmp_path / "out.mp4"
    crop = {"x": 3, "y": 5, "w": 101, "h": 57}
    assert ffmpeg_backend.trim_to_video(
        str(source), 0.0, 1.0, "Ultra", str(out),
        options={**_OPTIONS, "crop": crop})
    info = ffmpeg_backend.get_video_info(str(out))
    assert (info["width"], info["height"]) == (100, 56)


def test_manual_crop_keeps_its_shape_with_an_aspect_preset(source, tmp_path):
    out = tmp_path / "out.mp4"
    crop = {"x": 0, "y": 0, "w": 80, "h": 80}
    assert ffmpeg_backend.trim_to_video(
        str(source), 0.0, 1.0, "Ultra", str(out),
        options={**_OPTIONS, "crop": crop, "aspect_preset": "9:16"})
    info = ffmpeg_backend.get_video_info(str(out))
    assert (info["width"], info["height"]) == (80, 80)


def test_failed_export_leaves_no_file(source, tmp_path, monkeypatch):
    out = tmp_path / "out.mp4"
    out.write_bytes(b"half-written")
    # A colour that sanitize_color accepts but ffmpeg does not know:
    # drawtext fails to initialise and ffmpeg exits non-zero.
    caption = {"text": "x", "fontcolor": "notacolour", "start": 0, "end": 1}
    monkeypatch.setattr(encode, "_log_ffmpeg_failure", lambda *a: None)
    assert ffmpeg_backend.trim_to_video(
        str(source), 0.0, 1.0, "Low", str(out), text_layers=[caption],
        options=_OPTIONS) is None
    assert not Path(out).exists()
