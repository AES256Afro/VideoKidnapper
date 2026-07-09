# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Motion-tracked text: keyframe interpolation, ffmpeg expression
compilation, and the preview/export parity guarantee."""

import pytest

from videokidnapper.utils.keyframes import (
    compile_axis_expr, normalize_keyframes, position_at,
)

KFS = [
    {"t": 1.0, "x": 100, "y": 300},
    {"t": 3.0, "x": 500, "y": 260},
    {"t": 5.0, "x": 450, "y": 380},
]


# ---------------------------------------------------------------------------
# normalize
# ---------------------------------------------------------------------------

def test_normalize_sorts_by_time():
    shuffled = [KFS[2], KFS[0], KFS[1]]
    assert [k["t"] for k in normalize_keyframes(shuffled)] == [1.0, 3.0, 5.0]


def test_normalize_collapses_near_duplicates_later_wins():
    kfs = [{"t": 2.0, "x": 10, "y": 10}, {"t": 2.005, "x": 99, "y": 88}]
    out = normalize_keyframes(kfs)
    assert len(out) == 1
    assert out[0]["x"] == 99 and out[0]["y"] == 88


def test_normalize_empty():
    assert normalize_keyframes([]) == []
    assert normalize_keyframes(None) == []


# ---------------------------------------------------------------------------
# position_at
# ---------------------------------------------------------------------------

def test_position_clamps_before_first_and_after_last():
    assert position_at(KFS, 0.0) == (100, 300)
    assert position_at(KFS, 99.0) == (450, 380)


def test_position_exact_keyframes():
    assert position_at(KFS, 1.0) == (100, 300)
    assert position_at(KFS, 3.0) == (500, 260)


def test_position_midpoint_lerps():
    x, y = position_at(KFS, 2.0)      # halfway 1.0→3.0
    assert x == pytest.approx(300)
    assert y == pytest.approx(280)


def test_position_single_keyframe_is_static():
    kfs = [{"t": 2.0, "x": 42, "y": 24}]
    assert position_at(kfs, 0.0) == (42, 24)
    assert position_at(kfs, 9.0) == (42, 24)


def test_position_empty_returns_none():
    assert position_at([], 1.0) is None


# ---------------------------------------------------------------------------
# expression compile + PARITY: evaluating the compiled ffmpeg expression
# must match position_at at every sampled time.
# ---------------------------------------------------------------------------

def _eval_expr(expr, t):
    """Evaluate the compiled drawtext expression with ffmpeg semantics."""
    py = expr.replace("\\,", ",").replace("if(", "_if(")
    return eval(  # noqa: S307 - test-only, fully controlled input
        py, {"_if": lambda c, a, b: a if c else b,
             "lt": lambda a, b: a < b, "t": t})


@pytest.mark.parametrize("axis,key", [("x", "x"), ("y", "y")])
def test_expr_matches_position_at(axis, key):
    expr = compile_axis_expr(KFS, axis)
    for t in [0.0, 0.5, 1.0, 1.7, 2.0, 2.9, 3.0, 3.5, 4.999, 5.0, 8.0]:
        expected = position_at(KFS, t)[0 if axis == "x" else 1]
        assert _eval_expr(expr, t) == pytest.approx(expected, abs=0.01), t


def test_expr_single_keyframe_is_constant():
    assert compile_axis_expr([{"t": 2, "x": 42, "y": 7}], "x") == "42"
    assert compile_axis_expr([{"t": 2, "x": 42, "y": 7}], "y") == "7"


def test_expr_commas_escaped_for_drawtext():
    expr = compile_axis_expr(KFS, "x")
    assert "\\," in expr
    assert ",," not in expr


def test_expr_empty_returns_none():
    assert compile_axis_expr([], "x") is None


# ---------------------------------------------------------------------------
# drawtext integration
# ---------------------------------------------------------------------------

def _base_layer(**extra):
    layer = {"text": "hi", "fontsize": 24, "start": 0, "end": 6}
    layer.update(extra)
    return layer


def test_drawtext_uses_keyframe_expressions():
    from videokidnapper.core.ffmpeg.filters import _build_drawtext_filter
    out = _build_drawtext_filter(_base_layer(keyframes=KFS))
    assert "x='if(lt(t\\," in out
    assert "y='if(lt(t\\," in out


def test_drawtext_without_keyframes_unchanged():
    from videokidnapper.core.ffmpeg.filters import _build_drawtext_filter
    a = _build_drawtext_filter(_base_layer())
    b = _build_drawtext_filter(_base_layer(keyframes=[]))
    assert a == b
    assert "x=(w-tw)/2" in a


def test_drawtext_single_keyframe_static():
    from videokidnapper.core.ffmpeg.filters import _build_drawtext_filter
    out = _build_drawtext_filter(
        _base_layer(keyframes=[{"t": 1, "x": 120, "y": 80}]))
    assert "x='120'" in out and "y='80'" in out
