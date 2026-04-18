# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Tests for the ffmpeg ``eq=`` color-grade filter builder."""

from videokidnapper.core.ffmpeg_backend import (
    _assemble_video_filters, _build_eq_filter,
)


# ---------------------------------------------------------------------------
# Neutral / no-op detection
# ---------------------------------------------------------------------------

def test_no_options_returns_none():
    assert _build_eq_filter(None) is None
    assert _build_eq_filter({}) is None


def test_all_defaults_returns_none():
    opts = {
        "color_brightness": 0.0,
        "color_contrast":   1.0,
        "color_saturation": 1.0,
        "color_gamma":      1.0,
    }
    assert _build_eq_filter(opts) is None


def test_near_default_returns_none():
    # Within 0.001 of neutral — round-trip floating-point should not
    # produce an ffmpeg filter for what users perceive as "off".
    opts = {
        "color_brightness": 0.0005,
        "color_contrast":   1.0001,
        "color_saturation": 0.9998,
        "color_gamma":      1.0003,
    }
    assert _build_eq_filter(opts) is None


# ---------------------------------------------------------------------------
# Filter-string shape
# ---------------------------------------------------------------------------

def test_brightness_only():
    out = _build_eq_filter({"color_brightness": 0.2})
    assert out is not None
    assert "brightness=0.200" in out
    assert "contrast=1.000" in out
    assert "saturation=1.000" in out
    assert "gamma=1.000" in out
    assert out.startswith("eq=")


def test_all_four_axes():
    out = _build_eq_filter({
        "color_brightness": -0.3,
        "color_contrast":   1.5,
        "color_saturation": 1.8,
        "color_gamma":      0.75,
    })
    assert "brightness=-0.300" in out
    assert "contrast=1.500" in out
    assert "saturation=1.800" in out
    assert "gamma=0.750" in out


def test_out_of_range_values_are_clamped():
    # A corrupted settings file should NOT yield a filter ffmpeg would reject.
    out = _build_eq_filter({
        "color_brightness": 99.0,   # clamp to 1.0
        "color_contrast":   -50.0,  # clamp to 0.1
        "color_saturation": 99.0,   # clamp to 3.0
        "color_gamma":      0.001,  # clamp to 0.1
    })
    assert "brightness=1.000" in out
    assert "contrast=0.100" in out
    assert "saturation=3.000" in out
    assert "gamma=0.100" in out


def test_bad_types_return_none():
    # Non-numeric garbage from a hand-edited settings file → None,
    # not a crash. The encode path skips eq entirely.
    out = _build_eq_filter({
        "color_brightness": "abc",
    })
    assert out is None


# ---------------------------------------------------------------------------
# Filter-chain ordering
# ---------------------------------------------------------------------------

def test_eq_runs_between_rotate_and_speed():
    """Order guarantees: geometric ops → color → speed → drawtext → scale."""
    info = {"width": 1920, "height": 1080, "fps": 30.0}
    opts = {
        "rotate": 90,
        "speed":  2.0,
        "color_brightness": 0.2,
    }
    filters = _assemble_video_filters(
        preset_name="Medium", info=info, text_layers=[], options=opts,
    )
    kinds = [f.split("=", 1)[0] for f in filters]
    # rotate is transpose; speed is setpts; eq is eq; scale is scale.
    assert "transpose" in kinds
    assert "eq" in kinds
    assert "setpts" in kinds
    assert kinds.index("transpose") < kinds.index("eq") < kinds.index("setpts")


def test_neutral_eq_does_not_add_filter():
    info = {"width": 1920, "height": 1080, "fps": 30.0}
    opts = {"rotate": 0, "speed": 1.0}  # no color keys at all
    filters = _assemble_video_filters(
        preset_name="Medium", info=info, text_layers=[], options=opts,
    )
    assert not any(f.startswith("eq=") for f in filters)
