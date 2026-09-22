# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Captions and stickers export where the preview shows them.

Covers the three ways they used to drift:

1. The preview laid captions out on the raw source frame while the
   export drew them after the aspect crop / manual crop / blur fill /
   rotation. A caption that fit the 16:9 preview was sliced off at both
   edges of a 9:16 export.
2. drawtext never wraps, so any caption wider than the frame ran off it.
3. Stickers were composited after the final downscale, so at the Low
   preset they came out four times larger relative to the frame.
"""

import shutil
import subprocess

import pytest

from videokidnapper.core.ffmpeg.filters import (
    _assemble_video_filters, _build_final_scale,
)
from videokidnapper.core.frame_geometry import aspect_after_rotate, export_geometry
from videokidnapper.utils.text_wrap import available_width, wrap_text

HD = {"width": 1920, "height": 1080}


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------

def test_identity_geometry_is_the_source():
    g = export_geometry(HD, {})
    assert g.size == (1920, 1080)
    assert g.is_subrect and g.offset == (0, 0)


def test_aspect_crop_is_a_window_onto_the_source():
    g = export_geometry(HD, {"aspect_preset": "9:16"})
    assert g.size == (607, 1080)
    assert g.is_subrect
    assert g.offset == (656, 0)
    assert g.source_to_layout(656, 0) == (0, 0)
    assert g.layout_to_source(10, 20) == (666, 20)


def test_manual_crop_wins_over_aspect_preset():
    crop = {"x": 100, "y": 50, "w": 800, "h": 600}
    g = export_geometry(HD, {"aspect_preset": "9:16", "crop": crop})
    assert g.size == (800, 600)
    assert g.offset == (100, 50)


def test_blur_fill_canvas_and_foreground():
    g = export_geometry(HD, {"aspect_preset": "9:16", "aspect_fill_mode": "blur"})
    assert g.size == (606, 1080)
    assert not g.is_subrect
    fx, fy, fw, fh = g.steps[0].box
    assert fw == 606 and abs(fh - 341) <= 1
    assert fy == (1080 - fh) // 2 & ~1


@pytest.mark.parametrize("deg", [90, 180, 270])
def test_rotation_round_trips_points(deg):
    g = export_geometry(HD, {"rotate": deg})
    for pt in ((0, 0), (100, 40), (1919, 1079), (960, 540)):
        back = g.layout_to_source(*g.source_to_layout(*pt))
        assert back == pytest.approx(pt)


def test_rotate_90_turns_the_frame_clockwise():
    g = export_geometry(HD, {"rotate": 90})
    assert g.size == (1080, 1920)
    # The source's top-left corner ends up top-right.
    assert g.source_to_layout(0, 0) == (1080, 0)


def test_aspect_preset_applies_to_the_rotated_picture():
    """Landscape rotated 90° is already 9:16; nothing to crop.

    The old order cropped the landscape frame to 9:16 first, then rotated
    the strip to 16:9, and the final scale stretched it into 720x1280.
    """
    opts = {"aspect_preset": "9:16", "rotate": 90}
    assert aspect_after_rotate(opts)
    g = export_geometry(HD, opts)
    assert g.size == (1080, 1920)
    assert _assemble_video_filters("Medium", HD, [], opts) == [
        "transpose=1", "scale=720:1280",
    ]


def test_rotated_aspect_crop_is_centred_on_the_rotated_frame():
    opts = {"aspect_preset": "1:1", "rotate": 270}
    g = export_geometry(HD, opts)
    assert g.size == (1080, 1080)
    assert _assemble_video_filters("Medium", HD, [], opts)[:2] == [
        "transpose=2", "crop=1080:1080:0:420",
    ]


def test_render_matches_geometry_size():
    from PIL import Image
    frame = Image.new("RGB", (1920, 1080), (10, 20, 30))
    for opts in ({}, {"aspect_preset": "9:16"},
                 {"aspect_preset": "4:5", "aspect_fill_mode": "blur"},
                 {"rotate": 90}, {"aspect_preset": "1:1", "rotate": 270}):
        g = export_geometry(HD, opts)
        assert g.render(frame).size == g.size, opts


# ---------------------------------------------------------------------------
# Wrapping
# ---------------------------------------------------------------------------

def _chars(s):
    return 10.0 * len(s)   # every glyph 10 px wide


def test_short_text_is_left_alone():
    assert wrap_text("hello world", _chars, 500) == "hello world"


def test_wraps_at_word_boundaries():
    assert wrap_text("aaa bbb ccc ddd", _chars, 75) == "aaa bbb\nccc ddd"


def test_keeps_explicit_newlines():
    assert wrap_text("aaa bbb\nccc", _chars, 1000) == "aaa bbb\nccc"


def test_breaks_words_longer_than_a_line():
    assert wrap_text("abcdefghij", _chars, 40) == "abcd\nefgh\nij"


def test_budget_accounts_for_outline_and_box():
    base = available_width({}, 600)
    assert base == 600 - 40
    assert available_width({"borderw": 4}, 600) == base - 8
    assert available_width({"box": True, "boxborderw": 10}, 600) == base - 20


def test_dragged_caption_wraps_to_the_room_on_its_right():
    assert available_width({}, 1000, (300, 50)) == 1000 - 300 - 20
    # ...but never narrower than a quarter of the frame.
    assert available_width({}, 1000, (990, 50)) == 250


def test_drawtext_is_wrapped_to_the_layout_width():
    long_caption = "this caption is far too long to fit across a vertical frame"
    layer = {"text": long_caption, "fontsize": 64, "position": "(w-tw)/2:h-th-20"}
    wide = _assemble_video_filters("Ultra", HD, [layer], {})
    narrow = _assemble_video_filters("Ultra", HD, [layer], {"aspect_preset": "9:16"})
    draw_wide = next(f for f in wide if f.startswith("drawtext"))
    draw_narrow = next(f for f in narrow if f.startswith("drawtext"))
    assert "\n" not in draw_wide
    assert draw_narrow.count("\n") >= 2


def test_wrap_can_be_turned_off_per_layer():
    layer = {"text": "x " * 200, "fontsize": 64, "wrap": False}
    out = _assemble_video_filters("Ultra", HD, [layer], {"aspect_preset": "9:16"})
    assert "\n" not in next(f for f in out if f.startswith("drawtext"))


# ---------------------------------------------------------------------------
# Chain order and colour placement
# ---------------------------------------------------------------------------

def test_final_scale_can_be_split_off():
    opts = {"aspect_preset": "9:16"}
    pre = _assemble_video_filters("Medium", HD, [], opts, include_scale=False)
    assert pre == ["crop=607:1080:656:0"]
    assert _build_final_scale("Medium", HD, opts) == "scale=720:1280"


def test_crop_is_not_blown_up_past_its_own_size():
    crop = {"x": 0, "y": 0, "w": 600, "h": 400}
    assert _build_final_scale("Medium", HD, {"crop": crop}) is None


def test_hdr_is_normalised_after_geometry_before_text():
    hdr = dict(HD, color_transfer="arib-std-b67", color_space="bt2020nc",
               pix_fmt="yuv420p10le")
    layer = {"text": "hi", "fontsize": 30}
    out = _assemble_video_filters("Medium", hdr, [layer], {"aspect_preset": "1:1"})
    crop_i = next(i for i, f in enumerate(out) if f.startswith("crop="))
    color_i = next(i for i, f in enumerate(out)
                   if f.startswith(("zscale", "scale=in_color_matrix")))
    text_i = next(i for i, f in enumerate(out) if f.startswith("drawtext"))
    assert crop_i < color_i < text_i


def test_standard_sources_get_no_extra_colour_filter():
    tagged = dict(HD, color_space="bt709", color_range="tv", pix_fmt="yuv420p")
    assert _assemble_video_filters("Medium", tagged, [], {}) == ["scale=720:-2"]


# ---------------------------------------------------------------------------
# End to end with real ffmpeg
# ---------------------------------------------------------------------------

ffmpeg_missing = shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None


@pytest.fixture
def black_landscape(tmp_path):
    path = tmp_path / "black.mp4"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
         "color=black:s=1920x1080:r=24:d=1.2", "-c:v", "libx264",
         "-pix_fmt", "yuv420p", str(path)],
        check=True, capture_output=True)
    return path


def _frame(path, w, h):
    np = pytest.importorskip("numpy")
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", "0.5", "-i", str(path), "-frames:v", "1",
         "-f", "rawvideo", "-pix_fmt", "gray", "-"],
        capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(h, w)


@pytest.mark.skipif(ffmpeg_missing, reason="ffmpeg / ffprobe not on PATH")
def test_long_caption_stays_inside_a_vertical_export(black_landscape, tmp_path):
    """The user-visible bug: a caption sliced off by the 9:16 crop."""
    from videokidnapper.core.ffmpeg.encode import trim_to_video
    layer = {"text": "this caption is far too long to fit across a vertical frame",
             "fontsize": 64, "fontcolor": "white",
             "position": "(w-tw)/2:h-th-20", "start": 0, "end": 99}
    out = trim_to_video(str(black_landscape), 0, 1.0, "Medium",
                        str(tmp_path / "out.mp4"), text_layers=[layer],
                        options={"aspect_preset": "9:16", "hw_encoder": "off"})
    assert out
    frame = _frame(out, 720, 1280)
    ink = frame > 128
    assert ink.any(), "caption missing entirely"
    cols = ink.any(axis=0).nonzero()[0]
    # Inside the frame with its margin: nothing touches either edge.
    assert cols.min() > 5 and cols.max() < 720 - 5


@pytest.mark.skipif(ffmpeg_missing, reason="ffmpeg / ffprobe not on PATH")
def test_sticker_keeps_its_size_relative_to_the_frame(black_landscape, tmp_path):
    """400 px sticker on a 1920 px frame is ~21% of the width at any preset."""
    from PIL import Image

    from videokidnapper.core.ffmpeg.encode import trim_to_video
    sticker = tmp_path / "white.png"
    Image.new("RGBA", (400, 400), (255, 255, 255, 255)).save(sticker)
    out = trim_to_video(
        str(black_landscape), 0, 1.0, "Low", str(tmp_path / "out.mp4"),
        image_layers=[{"path": str(sticker), "position": "top_left", "scale": 1.0,
                       "start": 0, "end": 99}],
        options={"hw_encoder": "off"})
    assert out
    frame = _frame(out, 480, 270)
    cols = (frame > 128).any(axis=0).nonzero()[0]
    width_share = (cols.max() - cols.min() + 1) / 480
    assert width_share == pytest.approx(400 / 1920, abs=0.02)


def test_every_caption_position_is_clamped_inside_the_frame():
    """Drags near an edge and motion paths can't push text off."""
    layer = {"text": "hi", "fontsize": 40, "position": "1900:1070", "borderw": 3}
    draw = next(f for f in _assemble_video_filters("Ultra", HD, [layer], {})
                if f.startswith("drawtext"))
    # outline (3) + 2 px so the anti-aliased edge stays visible
    assert "x='clip(1900,5,max(5,w-tw-5))'" in draw
    assert "y='clip(1070,5,max(5,h-th-5))'" in draw


def test_caption_too_tall_for_the_frame_is_shrunk():
    from PIL import ImageFont

    from videokidnapper.ui.text_layers import _find_font_path
    from videokidnapper.utils.text_wrap import drawtext_layout, fit_layer_text

    path = _find_font_path("Arial")
    text, font, size = fit_layer_text(
        {}, " ".join(["caption"] * 40),
        lambda s: ImageFont.truetype(path, s), 220, 1920, 1080)
    assert size < 220
    lines = text.split("\n")
    assert drawtext_layout(font, text)[2] <= 1080 - 40
    assert max(font.getlength(line) for line in lines) <= 1920 - 40
