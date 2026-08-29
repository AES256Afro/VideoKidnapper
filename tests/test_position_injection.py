# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Hostile-payload tests for the filter-graph trust boundary.

``.vidkid`` project files are loaded without inspecting layer contents
and their fields flow into the ffmpeg filter graph. v1.8.1 closed the
colour-field injection (``fontcolor`` etc.); this suite pins the rest of
the boundary:

- ``position`` is interpolated bare into ``x=…:y=…`` — a crafted value
  could terminate the option (``:``), the filter (``,`` / ``;``), or the
  graph (``[``/``]``) and inject filters such as the file-reading
  ``movie=`` source. ``sanitize_position_expr`` must reject every shape
  the UI cannot produce.
- Corrupt numeric fields (fontsize, timing, boxborderw, keyframes, drag
  coords) must fail soft to defaults — never abort the encode.
- Legitimate values (all POSITION_MAP presets, numeric drag pairs,
  keyframed paths) must pass through unchanged.
"""
from videokidnapper.config import POSITION_MAP
from videokidnapper.core.ffmpeg.filters import _build_drawtext_filter
from videokidnapper.utils.ffmpeg_escape import (
    DEFAULT_POSITION,
    sanitize_position_expr,
)


# --- sanitize_position_expr: the allowlist itself ---------------------------

def test_all_position_map_presets_pass_through():
    for name, expr in POSITION_MAP.items():
        assert sanitize_position_expr(expr) == expr, name


def test_numeric_drag_positions_pass_through():
    for expr in ("0:0", "960:540", "-10:20", "12.5:45.75"):
        assert sanitize_position_expr(expr) == expr, expr


def test_injection_payloads_fall_back_to_default():
    payloads = [
        # Option injection: add a drawtext option that reads a local file.
        "0:0:textfile=/etc/passwd",
        # Filter injection via unescaped comma / semicolon.
        "0:0,movie=/etc/passwd",
        "0:0;movie=/etc/passwd",
        # Graph-structure injection.
        "0:0[evil]",
        "[a]overlay=0:0[b]",
        # Quote / backslash breakouts.
        "0:'0",
        "0:\\0",
        # Percent (drawtext expansion) and equals (option structure).
        "0:%{n}",
        "0=x:y",
        # Empty halves, no separator, too many separators, empty string.
        ":20", "20:", "0:0:0", "", "center",
        # Newline smuggling.
        "0:0\nmovie=/etc/passwd",
    ]
    for payload in payloads:
        assert sanitize_position_expr(payload) == DEFAULT_POSITION, payload


def test_non_string_positions_fall_back():
    for value in (None, 5, 3.14, ["0:0"], {"x": 0}, object()):
        assert sanitize_position_expr(value) == DEFAULT_POSITION, repr(value)


# --- through the drawtext builder: the graph stays intact -------------------

def _layer(**overrides):
    base = {
        "text": "hello",
        "fontsize": 24,
        "fontcolor": "white",
        "position": "960:540",
        "start": 0, "end": 5,
    }
    base.update(overrides)
    return base


def test_drawtext_position_injection_cannot_escape_the_option():
    filt = _build_drawtext_filter(_layer(position="0:0,movie=/etc/passwd"))
    # The hostile value must not appear; the fallback default must.
    assert "movie=" not in filt
    assert "/etc/passwd" not in filt
    assert "x=(w-tw)/2" in filt
    assert "y=h-th-20" in filt


def test_drawtext_legitimate_positions_render_unchanged():
    filt = _build_drawtext_filter(_layer(position="960:540"))
    assert "x=960" in filt
    assert "y=540" in filt
    filt = _build_drawtext_filter(_layer(position=POSITION_MAP["Top Left"]))
    assert "x=20" in filt and "y=20" in filt


def test_drawtext_corrupt_numbers_fail_soft():
    filt = _build_drawtext_filter(_layer(
        fontsize="huge", start="now", end="later", box=True,
        boxborderw="wide",
    ))
    # Defaults were substituted and the filter is still well-formed.
    assert "fontsize=24" in filt
    assert "between(t\\,0.0\\,999999)" in filt
    assert "boxborderw=8" in filt


def test_drawtext_corrupt_keyframes_fall_back_to_static_position():
    filt = _build_drawtext_filter(_layer(
        keyframes=[{"t": "not-a-number", "x": 0, "y": 0}],
        position="960:540",
    ))
    assert "x=960" in filt and "y=540" in filt


def test_drawtext_keyframed_path_still_compiles():
    filt = _build_drawtext_filter(_layer(keyframes=[
        {"t": 0, "x": 0, "y": 0},
        {"t": 2, "x": 100, "y": 50},
    ]))
    # Piecewise-linear expression, commas escaped for lavfi.
    assert "if(lt(t\\," in filt
    assert "movie=" not in filt
