# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Animated stickers animate in the preview, not just in the export.

The preview canvas composites one still per overlay with Pillow, so an
animated sticker used to sit on its first frame while the exported file
moved — the only place the app's preview/export parity rule did not
hold. `load_animation_frames` + `frame_index_at` close that.

On accuracy: measured against ffmpeg 6.0, the first loop of a
`-stream_loop -1` overlay runs ~0.133 s long and every loop after it is
exactly nominal, so the preview stays within about one sticker frame
and does not drift. These tests pin the frame *selection*; they do not
assert frame-exact parity with ffmpeg, which is not claimed.
"""

import pytest

from videokidnapper.utils.animated_media import (
    DEFAULT_FRAME_MS,
    MAX_PREVIEW_FRAME_PIXELS,
    frame_index_at,
    load_animation_frames,
)


PIL = pytest.importorskip("PIL", reason="Pillow required")


def _frames(count=10, size=(40, 40)):
    from PIL import Image, ImageDraw

    out = []
    for i in range(count):
        im = Image.new("RGBA", size, (0, 0, 0, 0))
        ImageDraw.Draw(im).rectangle([i, 0, i + 4, 8], fill=(255, 0, 0, 255))
        out.append(im)
    return out


@pytest.fixture
def gif(tmp_path):
    path = tmp_path / "s.gif"
    frames = _frames()
    frames[0].save(path, save_all=True, append_images=frames[1:],
                   duration=100, loop=0, disposal=2)
    return path


# ---------------------------------------------------------------- selection

def test_frame_advances_and_wraps():
    durations = [100] * 10          # ten frames, a one-second loop
    assert frame_index_at(durations, 0.00) == 0
    assert frame_index_at(durations, 0.05) == 0
    assert frame_index_at(durations, 0.15) == 1
    assert frame_index_at(durations, 0.95) == 9
    # Loops rather than running off the end.
    assert frame_index_at(durations, 1.00) == 0
    assert frame_index_at(durations, 2.35) == 3


def test_frame_selection_honours_per_frame_durations():
    """GIFs may hold individual frames longer than others."""
    durations = [500, 100, 100]
    assert frame_index_at(durations, 0.0) == 0
    assert frame_index_at(durations, 0.4) == 0     # still the long frame
    assert frame_index_at(durations, 0.55) == 1
    assert frame_index_at(durations, 0.65) == 2
    assert frame_index_at(durations, 0.70) == 0    # wrapped


@pytest.mark.parametrize("durations", [[], [0, 0]])
def test_degenerate_durations_do_not_divide_by_zero(durations):
    assert frame_index_at(durations, 1.0) == 0


def test_negative_time_is_clamped():
    assert frame_index_at([100, 100], -5.0) == 0


# ------------------------------------------------------------------ loading

def test_animated_gif_decodes_to_frames(gif):
    result = load_animation_frames(gif)
    assert result is not None
    frames, durations = result
    assert len(frames) == 10
    assert len(durations) == 10
    assert all(d > 0 for d in durations), "a zero duration would stall the loop"
    assert frames[0].mode == "RGBA"


def test_still_image_returns_none(tmp_path):
    from PIL import Image

    path = tmp_path / "still.png"
    Image.new("RGBA", (10, 10), (1, 2, 3, 255)).save(path)
    assert load_animation_frames(path) is None, "a still must use the cheap path"


def test_unreadable_file_returns_none(tmp_path):
    bad = tmp_path / "broken.gif"
    bad.write_bytes(b"not a gif at all")
    assert load_animation_frames(bad) is None
    assert load_animation_frames(tmp_path / "missing.gif") is None


def test_oversized_animation_is_refused(tmp_path, monkeypatch):
    """The budget is a memory guard: over it, the sticker previews as a
    still rather than the app holding hundreds of MB of RGBA."""
    monkeypatch.setattr(
        "videokidnapper.utils.animated_media.MAX_PREVIEW_FRAME_PIXELS", 100,
    )
    path = tmp_path / "big.gif"
    frames = _frames(count=4, size=(60, 60))   # 14400 px > 100
    frames[0].save(path, save_all=True, append_images=frames[1:],
                   duration=100, loop=0)
    assert load_animation_frames(path) is None


def test_zero_duration_frames_fall_back_to_a_sane_default(tmp_path):
    """Some GIFs report 0 ms, which would make the loop length zero."""
    from PIL import Image

    path = tmp_path / "zero.gif"
    frames = _frames(count=3)
    frames[0].save(path, save_all=True, append_images=frames[1:],
                   duration=0, loop=0)
    result = load_animation_frames(path)
    if result is not None:          # Pillow may normalise this itself
        _frames_out, durations = result
        assert all(d == DEFAULT_FRAME_MS or d > 0 for d in durations)


def test_budget_constant_is_sane():
    # Guards against someone "tidying" this to a value that would let a
    # single sticker allocate gigabytes.
    assert 1_000_000 < MAX_PREVIEW_FRAME_PIXELS < 200_000_000
