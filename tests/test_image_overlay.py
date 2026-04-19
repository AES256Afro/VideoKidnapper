# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Tests for the image / logo overlay filter-complex builder."""

from videokidnapper.core.ffmpeg_backend import (
    IMAGE_OVERLAY_POSITIONS, _build_image_overlay_chain,
    _overlay_position_expr,
)


# ---------------------------------------------------------------------------
# Position anchors
# ---------------------------------------------------------------------------

def test_all_declared_anchors_have_expressions():
    # Every anchor listed in the public constant must produce
    # x / y expressions — otherwise the UI menu can show an option
    # the core can't render.
    for anchor in IMAGE_OVERLAY_POSITIONS:
        x, y = _overlay_position_expr(anchor)
        assert x and y, f"anchor {anchor!r} produced empty expr"


def test_top_right_uses_main_w_overlay_w():
    x, y = _overlay_position_expr("top_right")
    assert "main_w-overlay_w" in x
    assert y == "20"


def test_center_centers_both_axes():
    x, y = _overlay_position_expr("center")
    assert "(main_w-overlay_w)/2" == x
    assert "(main_h-overlay_h)/2" == y


def test_unknown_anchor_falls_back_to_top_right():
    # The UI might send a newer anchor name the core hasn't added yet;
    # the fallback keeps the overlay visible instead of crashing.
    x, y = _overlay_position_expr("magic")
    assert "main_w-overlay_w" in x
    assert y == "20"


# ---------------------------------------------------------------------------
# Filter-complex chain construction
# ---------------------------------------------------------------------------

def test_no_layers_returns_empty_filter():
    fc, final, inputs = _build_image_overlay_chain([], base_label="v0")
    assert fc == ""
    assert final == "v0"
    assert inputs == []


def test_no_path_layers_are_skipped():
    # A layer with an empty path contributes nothing — the UI always
    # starts layers with path="" until the user picks a file.
    fc, final, inputs = _build_image_overlay_chain(
        [{"path": "", "position": "top_right", "scale": 0.25,
          "opacity": 1.0, "start": 0, "end": 5}],
        base_label="v0",
    )
    assert fc == ""
    assert final == "v0"
    assert inputs == []


def test_single_layer_produces_two_filter_parts():
    layers = [{
        "path": "/tmp/logo.png",
        "position": "top_right",
        "scale": 0.3,
        "opacity": 0.8,
        "start": 0.0,
        "end": 10.0,
    }]
    fc, final, inputs = _build_image_overlay_chain(
        layers, base_label="vbase", video_dur=10.0,
    )
    # One scale-and-alpha stage + one overlay stage = two ; -separated parts.
    assert fc.count(";") == 1
    assert "scale=iw*0.300:-1" in fc
    assert "colorchannelmixer=aa=0.800" in fc
    assert "overlay=x=main_w-overlay_w-20:y=20" in fc
    assert "enable='between(t\\,0.000\\,10.000)'" in fc
    assert final == "v_ov0"
    assert inputs == ["/tmp/logo.png"]


def test_two_layer_chain_threads_output_labels():
    layers = [
        {"path": "/tmp/a.png", "position": "top_left",
         "scale": 0.2, "opacity": 1.0, "start": 0, "end": 5},
        {"path": "/tmp/b.png", "position": "bottom_right",
         "scale": 0.3, "opacity": 0.5, "start": 2, "end": 8},
    ]
    fc, final, inputs = _build_image_overlay_chain(
        layers, base_label="vbase", video_dur=10.0,
    )
    # Each layer adds two filter parts (scale + overlay) → four total.
    assert fc.count(";") == 3
    # Second overlay must consume the output of the first.
    assert "[v_ov0][ov1s]overlay" in fc
    assert final == "v_ov1"
    assert inputs == ["/tmp/a.png", "/tmp/b.png"]


def test_out_of_range_values_are_clamped():
    layers = [{
        "path": "/tmp/z.png",
        "position": "center",
        "scale": 5.0,      # way too big — clamp to 1.0
        "opacity": -1.0,   # negative — clamp to 0.0
        "start": -10.0,    # negative — clamp to 0.0
        "end": 100.0,
    }]
    fc, _final, _inputs = _build_image_overlay_chain(
        layers, base_label="vbase", video_dur=5.0,
    )
    assert "scale=iw*1.000:-1" in fc
    assert "colorchannelmixer=aa=0.000" in fc
    assert "between(t\\,0.000\\,5.000)" in fc


def test_invalid_timing_drops_layer():
    layers = [{
        "path": "/tmp/bad.png",
        "position": "center",
        "scale": 0.2,
        "opacity": 1.0,
        "start": 5.0,
        "end": 5.0,   # zero-length → skip
    }]
    fc, final, inputs = _build_image_overlay_chain(
        layers, base_label="vbase", video_dur=10.0,
    )
    assert fc == ""
    assert final == "vbase"
    assert inputs == []


# ---------------------------------------------------------------------------
# Drag-override (explicit x / y)
# ---------------------------------------------------------------------------

def test_explicit_xy_overrides_anchor():
    # When the user has dragged the overlay, the layer dict carries
    # ``x`` and ``y`` in source-pixel space. These MUST win over the
    # anchor so the exported position matches the preview.
    x, y = _overlay_position_expr("center", x=120, y=240)
    assert x == "120"
    assert y == "240"


def test_explicit_xy_ignored_if_only_one_is_set():
    # Both axes must be provided to trigger the override — a lone
    # ``x`` with ``y=None`` is nonsense and falls back to anchor.
    x, y = _overlay_position_expr("center", x=100, y=None)
    assert "(main_w-overlay_w)/2" == x
    assert "(main_h-overlay_h)/2" == y


def test_explicit_negative_xy_clamped_to_zero():
    # A drag that started too close to the frame edge can produce a
    # negative coord; ffmpeg accepts it but the overlay would clip
    # off-canvas. Clamp defensively.
    x, y = _overlay_position_expr("top_left", x=-50, y=-10)
    assert x == "0"
    assert y == "0"


def test_drag_override_threads_into_filter_chain():
    # Drag-positioned overlay in a chain: the overlay filter must use
    # the explicit pixel coords, not ``main_w-overlay_w``-style exprs.
    layers = [{
        "path": "/tmp/logo.png",
        "position": "top_right",   # ignored because x/y win
        "x": 300, "y": 150,
        "scale": 0.25, "opacity": 1.0,
        "start": 0.0, "end": 5.0,
    }]
    fc, _final, _inputs = _build_image_overlay_chain(
        layers, base_label="vbase", video_dur=5.0,
    )
    assert "overlay=x=300:y=150" in fc
    # And the default anchor exprs must NOT appear for this layer.
    assert "main_w-overlay_w" not in fc
