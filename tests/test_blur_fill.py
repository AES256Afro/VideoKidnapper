# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Tests for the blurred-background aspect fill."""

from videokidnapper.core.ffmpeg.filters import (
    _assemble_video_filters, _build_aspect_fill_blur, _even,
)


_INFO_16_9 = {"width": 1920, "height": 1080, "has_audio": True}
_INFO_9_16 = {"width": 1080, "height": 1920, "has_audio": True}


def test_even_rounds_down():
    assert _even(607.5) == 606
    assert _even(608) == 608
    assert _even(3) == 2
    assert _even(1) == 2


def test_wide_source_to_portrait_keeps_height():
    out = _build_aspect_fill_blur("9:16", _INFO_16_9, None)
    # 1080 * 9/16 = 607.5 → even 606; height stays 1080.
    assert "scale=606:1080:force_original_aspect_ratio=increase" in out
    assert "crop=606:1080" in out
    assert "scale=606:1080:force_original_aspect_ratio=decrease" in out
    assert "overlay=(W-w)/2:(H-h)/2" in out


def test_tall_source_to_landscape_keeps_width():
    out = _build_aspect_fill_blur("16:9", _INFO_9_16, None)
    # 1080 / (16/9) = 607.5 → even 606; width stays 1080.
    assert "scale=1080:606:force_original_aspect_ratio=increase" in out


def test_blur_radius_scales_with_canvas():
    out = _build_aspect_fill_blur("9:16", _INFO_16_9, None)
    # min(606, 1080) // 20 = 30.
    assert "boxblur=30" in out


def test_same_ratio_is_noop():
    assert _build_aspect_fill_blur("16:9", _INFO_16_9, None) is None


def test_defers_to_explicit_crop():
    crop = {"x": 0, "y": 0, "w": 500, "h": 500}
    assert _build_aspect_fill_blur("9:16", _INFO_16_9, crop) is None


def test_invalid_inputs_are_noop():
    assert _build_aspect_fill_blur("garbage", _INFO_16_9, None) is None
    assert _build_aspect_fill_blur(None, _INFO_16_9, None) is None
    assert _build_aspect_fill_blur("9:0", _INFO_16_9, None) is None
    assert _build_aspect_fill_blur("9:16", {"width": 0, "height": 0}, None) is None


def test_internal_labels_are_self_contained():
    out = _build_aspect_fill_blur("9:16", _INFO_16_9, None)
    # Every label opened is consumed — nothing leaks into the outer graph.
    for label in ("[bfm]", "[bfb]", "[bfbg]", "[bffg]"):
        assert out.count(label) == 2


# ---------------------------------------------------------------------------
# Mode selection in _assemble_video_filters
# ---------------------------------------------------------------------------

def test_default_mode_still_crops():
    filters = _assemble_video_filters(
        "Medium", _INFO_16_9, None, {"aspect_preset": "9:16"})
    joined = ",".join(filters)
    assert "crop=607:1080" in joined
    assert "boxblur" not in joined


def test_blur_mode_swaps_in_the_fill():
    filters = _assemble_video_filters(
        "Medium", _INFO_16_9, None,
        {"aspect_preset": "9:16", "aspect_fill_mode": "blur"})
    joined = ",".join(filters)
    assert "boxblur" in joined
    assert "split=2[bfm][bfb]" in joined
    # The historical aspect-crop must NOT also run.
    assert "crop=607:1080" not in joined


def test_blur_mode_without_aspect_preset_is_noop():
    filters = _assemble_video_filters(
        "Medium", _INFO_16_9, None, {"aspect_fill_mode": "blur"})
    assert "boxblur" not in ",".join(filters)


def test_blur_segment_composes_with_other_filters():
    filters = _assemble_video_filters(
        "Medium", _INFO_16_9,
        [{"text": "hi", "position": "20:20", "start": 0, "end": 5}],
        {"aspect_preset": "9:16", "aspect_fill_mode": "blur", "speed": 2.0},
    )
    joined = ",".join(filters)
    # Blur fill first, then speed, then drawtext, then scale.
    assert joined.index("boxblur") < joined.index("setpts")
    assert joined.index("setpts") < joined.index("drawtext")


def test_ui_fill_choices_resolve_to_known_modes():
    from videokidnapper.ui.export_options import ASPECT_FILL_CHOICES
    assert [k for _l, k in ASPECT_FILL_CHOICES] == ["crop", "blur"]
