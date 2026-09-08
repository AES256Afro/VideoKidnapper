# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""An export with an aspect preset must come out at that exact ratio.

Cropping 1920x1080 to 9:16 gives a 607-wide frame; ``scale=720:-2`` on
that produced 720x1284 (and the blur-fill path 720x1282). Users read
that as "odd aspect ratio" — correctly. The final scale now targets the
canonical box for the preset width.
"""

import shutil
import subprocess

import pytest

from videokidnapper.core.ffmpeg.filters import (
    _assemble_video_filters,
    _build_aspect_crop,
    _build_aspect_scale,
)


LANDSCAPE = {"width": 1920, "height": 1080, "fps": 30, "duration": 3, "has_audio": False}
PORTRAIT  = {"width": 1080, "height": 1920, "fps": 30, "duration": 3, "has_audio": False}


@pytest.mark.parametrize("preset,aspect,info,expected", [
    ("Medium", "9:16", LANDSCAPE, "scale=720:1280"),   # was 720:-2 -> 720x1284
    ("Medium", "9:16", PORTRAIT,  "scale=720:1280"),   # matched: unchanged from before
    ("Medium", "1:1",  LANDSCAPE, "scale=720:720"),
    ("Medium", "16:9", LANDSCAPE, "scale=720:406"),    # same as -2 rounding gave
    ("Medium", "16:9", PORTRAIT,  "scale=720:406"),
    ("Low",    "9:16", LANDSCAPE, "scale=480:854"),
    ("High",   "9:16", LANDSCAPE, "scale=1080:1920"),
    ("Ultra",  "9:16", LANDSCAPE, "scale=606:1078"),   # no preset width: cropped frame, evened
    ("Ultra",  "9:16", PORTRAIT,  "scale=1080:1920"),
])
def test_exact_box(preset, aspect, info, expected):
    assert _build_aspect_scale(preset, aspect, info) == expected


def test_source_aspect_keeps_the_width_only_scale():
    filters = _assemble_video_filters("Medium", LANDSCAPE, [], {"aspect_preset": "Source"})
    assert filters[-1] == "scale=720:-2"


def test_assembler_uses_the_exact_box_with_an_aspect_preset():
    filters = _assemble_video_filters("Medium", LANDSCAPE, [], {"aspect_preset": "9:16"})
    assert filters[0].startswith("crop=607:1080")
    assert filters[-1] == "scale=720:1280"


def test_crop_string_is_unchanged():
    """The crop maths was factored out; the emitted string must not move."""
    assert _build_aspect_crop("9:16", LANDSCAPE, None) == "crop=607:1080:656:0"
    assert _build_aspect_crop("9:16", PORTRAIT, None) is None


def test_unparseable_aspect_is_ignored():
    assert _build_aspect_scale("Medium", "wide", LANDSCAPE) is None


ffmpeg_missing = shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None


@pytest.mark.skipif(ffmpeg_missing, reason="ffmpeg / ffprobe not on PATH")
@pytest.mark.parametrize("fill_mode", ["crop", "blur"])
def test_landscape_to_9_16_export_is_exactly_720x1280(tmp_path, fill_mode):
    from videokidnapper.core.ffmpeg.encode import trim_to_video

    src = tmp_path / "landscape.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
                    "-i", "testsrc=size=1920x1080:rate=30:duration=1.5",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(src)],
                   check=True, capture_output=True)
    out = tmp_path / f"out_{fill_mode}.mp4"
    result = trim_to_video(str(src), 0.1, 1.2, "Medium", str(out),
                           options={"aspect_preset": "9:16", "aspect_fill_mode": fill_mode,
                                    "hw_encoder": "off"})
    assert result and out.exists()
    dims = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                           "-show_entries", "stream=width,height", "-of", "csv=p=0", str(out)],
                          capture_output=True, text=True).stdout.strip()
    assert dims == "720,1280", f"{fill_mode}: got {dims}"
