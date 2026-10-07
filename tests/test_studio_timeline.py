# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Pure geometry behind the Studio timeline (no display needed)."""

import pytest

from videokidnapper.ui.studio.timeline import (
    LANES, MIN_CLIP_S, RULER_H, clamp_clip, format_tick, lane_at, lane_top,
    tick_step, time_to_x, total_height, transport_play_x, transport_timecode,
    view_window, x_to_time,
)


def test_time_and_x_round_trip():
    for t in (0.0, 3.25, 41.9):
        x = time_to_x(t, 0.0, 42.0, 112, 800)
        assert x_to_time(x, 0.0, 42.0, 112, 800) == pytest.approx(t)


def test_time_to_x_maps_view_edges():
    assert time_to_x(10.0, 10.0, 20.0, 100, 500) == 100
    assert time_to_x(20.0, 10.0, 20.0, 100, 500) == 600


def test_tick_step_keeps_labels_apart():
    step = tick_step(42.0, 800)
    assert step / 42.0 * 800 >= 70
    # A tighter step would crowd the labels.
    smaller = [s for s in (0.1, 0.2, 0.5, 1, 2, 5) if s < step]
    assert all(s / 42.0 * 800 < 70 for s in smaller)


def test_tick_step_handles_degenerate_input():
    assert tick_step(0, 800) > 0
    assert tick_step(10, 0) > 0


def test_format_tick():
    assert format_tick(65, 5) == "1:05"
    assert format_tick(3.5, 0.5) == "0:03.5"
    assert format_tick(-1, 1) == "0:00"


def test_view_window_full_clip_at_zoom_one():
    assert view_window(42.0, 1.0, 30.0) == (0.0, 42.0)


def test_view_window_zoomed_follows_focus_without_overscroll():
    start, end = view_window(40.0, 4.0, 20.0)
    assert end - start == pytest.approx(10.0)
    assert start <= 20.0 <= end
    # Focus near the end pins the window to the clip's end.
    start, end = view_window(40.0, 4.0, 39.0)
    assert end == pytest.approx(40.0)
    start, end = view_window(40.0, 4.0, 0.5)
    assert start == pytest.approx(0.0)


def test_view_window_empty_clip():
    assert view_window(0, 3, 0) == (0.0, 1.0)


def test_clamp_clip_move_keeps_length_inside_clip():
    assert clamp_clip(5, 9, 42, "move", 2) == (7, 11)
    assert clamp_clip(5, 9, 42, "move", 100) == (38, 42)
    assert clamp_clip(5, 9, 42, "move", -100) == (0, 4)


def test_clamp_clip_resize_respects_minimum():
    start, end = clamp_clip(5, 9, 42, "start", 10)
    assert end == 9 and end - start == pytest.approx(MIN_CLIP_S)
    start, end = clamp_clip(5, 9, 42, "end", -10)
    assert start == 5 and end - start == pytest.approx(MIN_CLIP_S)
    assert clamp_clip(5, 9, 42, "end", 100) == (5, 42)


def test_lanes_stack_below_the_ruler():
    assert lane_at(0) == "ruler"
    top = RULER_H
    for key, _label, height in LANES:
        assert lane_at(top) == key
        assert lane_at(top + height - 1) == key
        assert lane_top(key) == (top, height)
        top += height
    assert lane_at(top) is None
    assert total_height() == top


def test_transport_timecode_full_and_compact():
    assert transport_timecode(2.8, 6.0) == "00:00:02.800   /   00:00:06.000"
    assert transport_timecode(2.8, 6.0, compact=True) == "00:02.800 / 00:06.000"
    # An hour-long clip keeps its hours even when compact.
    assert transport_timecode(5.0, 3725.5, compact=True) == "00:00:05.000 / 01:02:05.500"


def test_transport_timecode_placeholder_keeps_its_shape():
    full = transport_timecode(None, None)
    assert full == "--:--:--.---   /   --:--:--.---"
    assert len(full) == len(transport_timecode(1.0, 2.0))
    assert len(transport_timecode(None, None, compact=True)) == len(
        transport_timecode(1.0, 2.0, compact=True))


def test_transport_play_x_prefers_true_centre():
    assert transport_play_x(900, left=280, play=200, right=200) == 450


def test_transport_play_x_shifts_into_free_space_when_crowded():
    # 640 wide: centred controls (220..420) would hit the 300-px timecode.
    x = transport_play_x(640, left=300, play=200, right=100)
    assert x == pytest.approx((312 + 528) / 2)
    assert x - 100 >= 312 and x + 100 <= 528


def test_transport_play_x_reports_no_fit():
    assert transport_play_x(520, left=300, play=200, right=200) is None


def test_transport_timecode_rounds_to_the_nearest_millisecond():
    assert transport_timecode(2.9996, 6.0, compact=True) == "00:03.000 / 00:06.000"
    assert transport_timecode(1.2, 59.9999, compact=True) == "00:01.200 / 01:00.000"
