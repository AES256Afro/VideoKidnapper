# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""The preview's approximation of the export color grade."""

from PIL import Image

from videokidnapper.utils.color_preview import apply_grade, build_lut, is_neutral


def _swatch(rgb=(200, 60, 40)):
    return Image.new("RGB", (4, 4), rgb)


def test_neutral_returns_same_image():
    img = _swatch()
    assert apply_grade(img) is img
    assert is_neutral(0.0, 1.0, 1.0, 1.0)


def test_identity_lut():
    assert build_lut(0.0, 1.0, 1.0) == list(range(256))


def test_low_saturation_pulls_toward_gray():
    r, g, b = apply_grade(_swatch(), saturation=0.2).getpixel((0, 0))
    assert max(r, g, b) - min(r, g, b) < 160 * 0.3


def test_zero_saturation_is_gray():
    r, g, b = apply_grade(_swatch(), saturation=0.0).getpixel((0, 0))
    assert r == g == b


def test_brightness_lifts_values():
    base = _swatch((100, 100, 100))
    assert apply_grade(base, brightness=0.2).getpixel((0, 0))[0] > 140


def test_contrast_stretches_around_mid_gray():
    dark = apply_grade(_swatch((60, 60, 60)), contrast=2.0).getpixel((0, 0))[0]
    light = apply_grade(_swatch((200, 200, 200)), contrast=2.0).getpixel((0, 0))[0]
    assert dark < 60 and light > 200


def test_gamma_above_one_brightens_midtones():
    out = apply_grade(_swatch((128, 128, 128)), gamma=2.0).getpixel((0, 0))[0]
    assert out > 128


def test_out_of_range_values_are_clamped_like_export():
    # Mirrors _build_eq_filter's clamps rather than crashing or wrapping.
    img = apply_grade(_swatch(), brightness=5, contrast=-1, saturation=9, gamma=0)
    assert img.size == (4, 4)
