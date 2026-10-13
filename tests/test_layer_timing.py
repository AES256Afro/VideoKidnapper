# SPDX-FileCopyrightText: 2026 AES256Afro <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Layers move from the editor's source clock onto the export's clock."""

import pytest

from videokidnapper.core.ffmpeg.layer_timing import layers_for_range
from videokidnapper.utils.keyframes import position_at


def _layer(start, end, **extra):
    return {"text": "hi", "start": start, "end": end, **extra}


def test_range_start_becomes_zero():
    (timed,) = layers_for_range([_layer(12.0, 14.0)], start=10.0, end=20.0)
    assert (timed["start"], timed["end"]) == pytest.approx((2.0, 4.0))


def test_speed_divides_the_times():
    (timed,) = layers_for_range([_layer(12.0, 14.0)], 10.0, 20.0, speed=2.0)
    assert (timed["start"], timed["end"]) == pytest.approx((1.0, 2.0))
    (slow,) = layers_for_range([_layer(12.0, 14.0)], 10.0, 20.0, speed=0.5)
    assert (slow["start"], slow["end"]) == pytest.approx((4.0, 8.0))


def test_layers_outside_the_range_are_dropped():
    layers = [_layer(0.0, 5.0), _layer(20.0, 25.0), _layer(9.0, 10.0), _layer(15.0, 16.0)]
    timed = layers_for_range(layers, 10.0, 20.0)
    assert [(t["start"], t["end"]) for t in timed] == [(5.0, 6.0)]


def test_layers_are_clipped_to_the_range():
    (timed,) = layers_for_range([_layer(5.0, 30.0)], 10.0, 20.0)
    assert (timed["start"], timed["end"]) == (0.0, 10.0)


def test_open_ended_layer_runs_to_the_end_of_the_clip():
    (timed,) = layers_for_range([{"text": "hi"}], 10.0, 16.0, speed=2.0)
    assert (timed["start"], timed["end"]) == pytest.approx((0.0, 3.0))


def test_input_is_not_modified():
    layer = _layer(12.0, 14.0, keyframes=[{"t": 12.0, "x": 0, "y": 0}])
    before = repr(layer)
    layers_for_range([layer], 10.0, 20.0, speed=2.0)
    assert repr(layer) == before


def test_garbage_is_tolerated():
    layers = [None, "x", _layer("soon", "later"), _layer(11, 12)]
    timed = layers_for_range(layers, 10.0, 20.0, speed="fast")
    # "soon"/"later" read as 0 and open-ended: the whole clip.
    assert [(t["start"], t["end"]) for t in timed] == [(0.0, 10.0), (1.0, 2.0)]
    assert layers_for_range([_layer(1, 2)], 5.0, 5.0) == []
    assert layers_for_range(None, 0, 10) == []


def test_motion_path_is_unchanged_inside_the_range():
    path = [{"t": 0.0, "x": 0.0, "y": 0.0},
            {"t": 12.0, "x": 120.0, "y": 60.0},
            {"t": 30.0, "x": 300.0, "y": 0.0}]
    (timed,) = layers_for_range([_layer(0.0, 40.0, keyframes=path)],
                                10.0, 20.0, speed=2.0)
    new_path = timed["keyframes"]
    assert new_path[0]["t"] == 0.0 and new_path[-1]["t"] == pytest.approx(5.0)
    assert all(kf["t"] >= 0 for kf in new_path)
    for source_t in (10.0, 11.0, 12.0, 15.5, 19.9, 20.0):
        out_t = (source_t - 10.0) / 2.0
        assert position_at(new_path, out_t) == pytest.approx(position_at(path, source_t))


def test_corrupt_motion_path_falls_back_to_static():
    (timed,) = layers_for_range(
        [_layer(0.0, 40.0, keyframes=[{"t": "x"}])], 10.0, 20.0)
    assert timed["keyframes"] == []
