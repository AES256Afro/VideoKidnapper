# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Tests for numeric custom-position parsing used by drag-to-position."""

from videokidnapper.ui.video_player import (
    _parse_numeric_position, _resolve_position,
)


def test_numeric_parse_integer_pair():
    assert _parse_numeric_position("100:200") == (100, 200)


def test_numeric_parse_float_pair_rounds():
    assert _parse_numeric_position("12.9:45.1") == (12, 45)


def test_numeric_parse_zero():
    assert _parse_numeric_position("0:0") == (0, 0)


def test_numeric_parse_empty_string_returns_none():
    assert _parse_numeric_position("") is None


def test_numeric_parse_none_returns_none():
    assert _parse_numeric_position(None) is None


def test_numeric_parse_rejects_ffmpeg_expressions():
    # These are the preset expressions built elsewhere — must NOT be treated
    # as numeric, else preview falls back to bottom-center.
    # ("20:20" — the top-left preset — IS numerically parseable, but that's
    #  intentional: both branches resolve to the same pixel at default pad.)
    for expr in (
        "(w-tw)/2:h-th-20",
        "w-tw-20:h-th-20",
        "20:h-th-20",
        "(w-tw)/2:(h-th)/2",
    ):
        assert _parse_numeric_position(expr) is None, expr


def test_top_left_preset_parses_numerically_to_same_spot():
    # "20:20" is both the top-left preset and a valid custom position; they
    # must render at the same coordinates so the collapse is harmless.
    numeric = _parse_numeric_position("20:20")
    via_resolve = _resolve_position("20:20", 1920, 1080, 100, 40, pad=20)
    assert numeric == (20, 20)
    assert via_resolve == (20, 20)


def test_numeric_parse_single_value_no_colon():
    assert _parse_numeric_position("100") is None


def test_resolve_numeric_returns_custom_coords_directly():
    # Should bypass preset pattern matching.
    x, y = _resolve_position("300:450", 1920, 1080, 100, 40)
    assert (x, y) == (300, 450)


def test_resolve_preset_unaffected_by_numeric_branch():
    # A known preset still resolves to its pad-aware location.
    w, h, tw, th = 1920, 1080, 200, 50
    x, y = _resolve_position("(w-tw)/2:h-th-20", w, h, tw, th, pad=20)
    assert x == (w - tw) // 2
    assert y == h - th - 20
