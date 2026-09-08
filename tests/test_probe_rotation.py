# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""get_video_info must report *displayed* dimensions, not stored ones.

Phone footage is stored landscape with a Display Matrix telling players
to rotate it. ffmpeg honours that on decode, so the preview and every
export frame come out portrait — but the probe read the raw width and
height, so the app reasoned about geometry in the wrong orientation.
A 9:16 preset on an already-9:16 phone clip computed a crop wider than
the frame and ffmpeg produced a mangled 720x1284.
"""

import json
import shutil
import subprocess
from unittest import mock

import pytest

from videokidnapper.core.ffmpeg import probe


def _ffprobe_json(width, height, side_data=None, tags=None):
    stream = {"codec_type": "video", "width": width, "height": height,
              "r_frame_rate": "30/1"}
    if side_data is not None:
        stream["side_data_list"] = side_data
    if tags is not None:
        stream["tags"] = tags
    return json.dumps({"streams": [stream], "format": {"duration": "3.0"}})


def _info_for(payload):
    fake = mock.Mock(returncode=0, stdout=payload, stderr="")
    with mock.patch.object(probe.subprocess, "run", return_value=fake), \
         mock.patch.object(probe, "_get_ffprobe", return_value="ffprobe"):
        return probe.get_video_info("x.mp4")


@pytest.mark.parametrize("rotation", [90, -90, 270, -270, 90.0, "90"])
def test_quarter_turn_swaps_dimensions(rotation):
    info = _info_for(_ffprobe_json(
        1920, 1080, side_data=[{"side_data_type": "Display Matrix", "rotation": rotation}],
    ))
    assert (info["width"], info["height"]) == (1080, 1920)


@pytest.mark.parametrize("rotation", [0, 180, -180, 360])
def test_half_turn_or_none_keeps_dimensions(rotation):
    info = _info_for(_ffprobe_json(
        1920, 1080, side_data=[{"side_data_type": "Display Matrix", "rotation": rotation}],
    ))
    assert (info["width"], info["height"]) == (1920, 1080)


def test_legacy_rotate_tag_is_honoured():
    info = _info_for(_ffprobe_json(1920, 1080, tags={"rotate": "90"}))
    assert (info["width"], info["height"]) == (1080, 1920)


def test_display_matrix_wins_over_tag():
    info = _info_for(_ffprobe_json(
        1920, 1080,
        side_data=[{"side_data_type": "Display Matrix", "rotation": 0}],
        tags={"rotate": "90"},
    ))
    assert (info["width"], info["height"]) == (1920, 1080)


def test_other_side_data_is_ignored():
    info = _info_for(_ffprobe_json(
        1920, 1080, side_data=[{"side_data_type": "Spherical Mapping"}],
    ))
    assert (info["width"], info["height"]) == (1920, 1080)


@pytest.mark.parametrize("bad", ["sideways", None, ""])
def test_garbage_rotation_means_no_rotation(bad):
    info = _info_for(_ffprobe_json(1920, 1080, tags={"rotate": bad}))
    assert (info["width"], info["height"]) == (1920, 1080)


def test_no_video_stream_still_returns_zeros():
    payload = json.dumps({"streams": [{"codec_type": "audio"}], "format": {"duration": "1"}})
    info = _info_for(payload)
    assert (info["width"], info["height"]) == (0, 0)


# ------------------------------------------------------------ real ffmpeg

ffmpeg_missing = shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None


@pytest.mark.skipif(ffmpeg_missing, reason="ffmpeg / ffprobe not on PATH")
def test_real_display_matrix_file(tmp_path):
    """End to end: a landscape-stored file with a 90° display matrix must
    probe as portrait, and a 9:16 preset must then leave it alone."""
    from videokidnapper.core.ffmpeg.filters import _build_aspect_crop

    plain = tmp_path / "plain.mp4"
    phone = tmp_path / "phone.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
                    "-i", "testsrc=size=1920x1080:rate=30:duration=1",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(plain)],
                   check=True, capture_output=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-display_rotation", "90",
                    "-i", str(plain), "-c", "copy", str(phone)],
                   check=True, capture_output=True)

    info = probe.get_video_info(str(phone))
    assert (info["width"], info["height"]) == (1080, 1920)
    assert _build_aspect_crop("9:16", info, None) is None, \
        "an already-9:16 clip must not be cropped by the 9:16 preset"

    # And the decoded frame agrees with the probe, so preview == export.
    frame = probe.extract_frame(str(phone), 0.5)
    assert frame.size == (info["width"], info["height"])
