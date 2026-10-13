# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Move text and image layers from source time onto an export's clock.

The editor stores a layer's ``start``/``end`` (and a motion path's
keyframe ``t``) in source time, the same clock as the player, so the
preview can compare them with the playhead directly. ffmpeg sees
something else: the input is seeked with ``-ss`` (its timestamps then
start at 0) and the speed change runs before the text and overlays, so
the filters' ``t`` is *output* time. A caption at 12–14 s exported from
a range starting at 10 s at 2x speed has to be enabled at 1–2 s.

:func:`layers_for_range` does that conversion once, before the filter
builders run, so every export path gets it.
"""

from videokidnapper.core.ffmpeg.filters import coerce_speed
from videokidnapper.utils.coerce import coerce_float


# A layer with no end runs to the end of the clip.
_OPEN_END = 1e9


def layers_for_range(layers, start, end, speed=1.0):
    """Copies of ``layers`` timed for the export of ``[start, end)``.

    Layers that end before the range or start after it are dropped; the
    rest are clipped to the range, shifted so the range starts at 0 and
    divided by ``speed``. Keyframes get the same treatment, with the path
    position at each edge of the range added as a keyframe so the motion
    inside the range is unchanged. The input list is not modified.
    """
    if not layers:
        return []
    speed = coerce_speed(speed)
    start = max(0.0, coerce_float(start, 0.0))
    end = coerce_float(end, start)
    if not end > start:
        return []

    def out_time(t):
        return (t - start) / speed

    timed = []
    for layer in layers:
        if not isinstance(layer, dict):
            continue
        layer_start = coerce_float(layer.get("start", 0.0), 0.0)
        layer_end = coerce_float(layer.get("end", _OPEN_END), _OPEN_END)
        layer_start = max(layer_start, start)
        layer_end = min(layer_end, end)
        if layer_end <= layer_start:
            continue
        copy = dict(layer)
        copy["start"] = out_time(layer_start)
        copy["end"] = out_time(layer_end)
        if layer.get("keyframes"):
            copy["keyframes"] = _keyframes_for_range(
                layer["keyframes"], start, end, out_time)
        timed.append(copy)
    return timed


def _keyframes_for_range(keyframes, start, end, out_time):
    """The part of a motion path inside the range, on the output clock."""
    from videokidnapper.utils.keyframes import normalize_keyframes, position_at

    try:
        kfs = normalize_keyframes(keyframes)
    except (KeyError, TypeError, ValueError):
        # Corrupt path: the drawtext builder falls back to the layer's
        # static position for an empty list, the same as it does for a
        # path it cannot compile.
        return []
    if not kfs:
        return []
    inside = [kf for kf in kfs if start < kf["t"] < end]
    edges = []
    for t in (start, end):
        x, y = position_at(kfs, t)
        edges.append({"t": t, "x": x, "y": y})
    path = [edges[0], *inside, edges[1]]
    return [{"t": out_time(kf["t"]), "x": kf["x"], "y": kf["y"]} for kf in path]
