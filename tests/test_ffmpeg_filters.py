# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
from videokidnapper.core.ffmpeg_backend import (
    _build_audio_speed, _build_crop_filter, _build_rotate_filter,
    _build_speed_filter,
)


def test_rotate_90():
    assert _build_rotate_filter(90) == "transpose=1"


def test_rotate_180():
    assert _build_rotate_filter(180) == "transpose=1,transpose=1"


def test_rotate_270():
    assert _build_rotate_filter(270) == "transpose=2"


def test_rotate_zero_returns_none():
    assert _build_rotate_filter(0) is None
    assert _build_rotate_filter(None) is None


def test_speed_identity_returns_none():
    assert _build_speed_filter(1.0) is None
    assert _build_speed_filter(None) is None


def test_speed_2x():
    f = _build_speed_filter(2.0)
    assert f.startswith("setpts=0.5000")


def test_audio_speed_chains_beyond_range():
    # 4x requires atempo=2.0 * atempo=2.0
    f = _build_audio_speed(4.0)
    assert f.count("atempo=") >= 2


def test_crop_returns_none_when_missing():
    info = {"width": 1920, "height": 1080}
    assert _build_crop_filter(None, info) is None


def test_crop_clamps_tiny():
    info = {"width": 100, "height": 100}
    # w=0 is invalid; builder should clamp to at least 2
    out = _build_crop_filter({"x": 0, "y": 0, "w": 0, "h": 0}, info)
    assert out.startswith("crop=2:2:")


def test_drawtext_runs_before_scale():
    """Drag-to-position only matches the preview if drawtext is applied
    before scale. A 1080p → 720p preset change must not shift text.
    """
    from videokidnapper.core.ffmpeg_backend import _assemble_video_filters

    info = {"width": 1920, "height": 1080}
    layer = {
        "text": "hi", "font": "Arial", "fontsize": 24,
        "fontcolor": "white", "position": "960:540",
        "box": False, "start": 0, "end": 5,
    }
    filters = _assemble_video_filters(
        "Medium", info, [layer], {"aspect_preset": "Source"},
    )
    drawtext_idx = next(i for i, f in enumerate(filters) if f.startswith("drawtext"))
    scale_idx = next(
        (i for i, f in enumerate(filters) if f.startswith("scale=")), -1,
    )
    # scale is only present when source > preset width (1920 > 720 here).
    assert scale_idx != -1
    assert drawtext_idx < scale_idx, (
        f"drawtext@{drawtext_idx} must come before scale@{scale_idx} — "
        "custom positions are in source-pixel coords."
    )
