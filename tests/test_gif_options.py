# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Tests for the GIF palette builders and loop-flag normalisation."""

from videokidnapper.core.ffmpeg.filters import (
    GIF_DITHER_PARAMS,
    _build_palettegen_filter,
    _build_paletteuse_filter,
    _gif_loop_flag,
)


# ---------------------------------------------------------------------------
# palettegen
# ---------------------------------------------------------------------------

def test_palettegen_default_matches_historical_string():
    # The pre-options pipeline emitted exactly this — defaults must not
    # change existing users' output.
    assert _build_palettegen_filter(256) == "palettegen=max_colors=256"
    assert _build_palettegen_filter(128) == "palettegen=max_colors=128"


def test_palettegen_full_stats_mode_is_omitted():
    # "full" is ffmpeg's own default; emitting it would churn the command
    # line for no behavior change.
    assert "stats_mode" not in _build_palettegen_filter(256, "full")


def test_palettegen_diff_stats_mode():
    assert (_build_palettegen_filter(256, "diff")
            == "palettegen=max_colors=256:stats_mode=diff")


def test_palettegen_unknown_stats_mode_falls_back():
    assert "stats_mode" not in _build_palettegen_filter(256, "bogus")
    assert "stats_mode" not in _build_palettegen_filter(256, None)


def test_palettegen_clamps_colors():
    assert _build_palettegen_filter(9999) == "palettegen=max_colors=256"
    assert _build_palettegen_filter(0) == "palettegen=max_colors=2"
    assert _build_palettegen_filter(-5) == "palettegen=max_colors=2"


# ---------------------------------------------------------------------------
# paletteuse
# ---------------------------------------------------------------------------

def test_paletteuse_default_matches_historical_string():
    assert (_build_paletteuse_filter()
            == "paletteuse=dither=bayer:bayer_scale=5")
    assert _build_paletteuse_filter("bayer") == _build_paletteuse_filter()


def test_paletteuse_floyd_steinberg():
    assert (_build_paletteuse_filter("floyd_steinberg")
            == "paletteuse=dither=floyd_steinberg")


def test_paletteuse_sierra():
    assert (_build_paletteuse_filter("sierra2_4a")
            == "paletteuse=dither=sierra2_4a")


def test_paletteuse_none():
    assert _build_paletteuse_filter("none") == "paletteuse=dither=none"


def test_paletteuse_unknown_dither_falls_back_to_bayer():
    # A hand-edited settings file must not be able to produce a command
    # ffmpeg rejects.
    assert (_build_paletteuse_filter("ordered8")
            == "paletteuse=dither=bayer:bayer_scale=5")
    assert (_build_paletteuse_filter(None)
            == "paletteuse=dither=bayer:bayer_scale=5")


def test_every_registered_dither_produces_a_dither_param():
    for key in GIF_DITHER_PARAMS:
        assert "dither=" in _build_paletteuse_filter(key)


# ---------------------------------------------------------------------------
# loop flag
# ---------------------------------------------------------------------------

def test_loop_forever_is_zero():
    assert _gif_loop_flag(0) == 0


def test_loop_once_is_minus_one():
    assert _gif_loop_flag(-1) == -1


def test_loop_n_times_passes_through():
    assert _gif_loop_flag(2) == 2
    assert _gif_loop_flag(5) == 5


def test_loop_accepts_numeric_strings():
    # Settings JSON round-trips ints fine, but be liberal in what we accept.
    assert _gif_loop_flag("3") == 3
    assert _gif_loop_flag("-1") == -1


def test_loop_garbage_falls_back_to_forever():
    assert _gif_loop_flag(None) == 0
    assert _gif_loop_flag("forever") == 0
    assert _gif_loop_flag(-7) == 0


# ---------------------------------------------------------------------------
# UI label registries stay in sync with the backend
# ---------------------------------------------------------------------------

def test_ui_dither_choices_resolve_to_backend_keys():
    from videokidnapper.ui.export_options import GIF_DITHER_CHOICES
    for _label, key in GIF_DITHER_CHOICES:
        assert key in GIF_DITHER_PARAMS


def test_ui_stats_choices_are_valid():
    from videokidnapper.core.ffmpeg.filters import GIF_STATS_MODES
    from videokidnapper.ui.export_options import GIF_STATS_CHOICES
    for _label, key in GIF_STATS_CHOICES:
        assert key in GIF_STATS_MODES


def test_ui_loop_choices_normalise_to_themselves():
    from videokidnapper.ui.export_options import GIF_LOOP_CHOICES
    for _label, value in GIF_LOOP_CHOICES:
        assert _gif_loop_flag(value) == value
