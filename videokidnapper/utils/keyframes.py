# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Keyframed motion paths for text layers (meme-style tracked captions).

A keyframe list is ``[{"t": seconds, "x": px, "y": px}, ...]`` in source-
pixel space — the same space the drag handler and the numeric "<x>:<y>"
custom position already use. Between keyframes the position interpolates
linearly; before the first and after the last it clamps.

Two consumers, one source of truth:

- the live preview calls :func:`position_at` per frame, and
- the export calls :func:`compile_axis_expr` to compile the SAME
  piecewise-linear path into an ffmpeg drawtext ``x=``/``y=`` expression.

The parity test evaluates the compiled expression and asserts it matches
``position_at`` — preview and export cannot drift apart.

Times ride the same clock as a layer's ``start``/``end`` (the player's
source-time), so whatever holds for ``enable=between(t,...)`` holds for
the motion path identically.
"""


def normalize_keyframes(keyframes):
    """Sorted-by-time copy with near-duplicate times (< 10 ms) collapsed.

    Later entries win a collision, which makes "drag again at the same
    frame" mean "replace", the intuitive editing behavior.
    """
    cleaned = []
    for kf in sorted(keyframes or [], key=lambda k: float(k["t"])):
        entry = {"t": float(kf["t"]), "x": float(kf["x"]), "y": float(kf["y"])}
        if cleaned and abs(entry["t"] - cleaned[-1]["t"]) < 0.01:
            cleaned[-1] = entry
        else:
            cleaned.append(entry)
    return cleaned


def position_at(keyframes, t):
    """``(x, y)`` of the path at time ``t`` — lerp inside, clamp outside."""
    kfs = normalize_keyframes(keyframes)
    if not kfs:
        return None
    t = float(t)
    if t <= kfs[0]["t"]:
        return (kfs[0]["x"], kfs[0]["y"])
    if t >= kfs[-1]["t"]:
        return (kfs[-1]["x"], kfs[-1]["y"])
    for a, b in zip(kfs, kfs[1:]):
        if a["t"] <= t <= b["t"]:
            span = b["t"] - a["t"]
            frac = 0.0 if span <= 0 else (t - a["t"]) / span
            return (a["x"] + (b["x"] - a["x"]) * frac,
                    a["y"] + (b["y"] - a["y"]) * frac)
    return (kfs[-1]["x"], kfs[-1]["y"])   # unreachable, defensive


def simplify_keyframes(keyframes, tolerance_px=3.0):
    """Drop keyframes that a straight line already explains.

    Ramer-Douglas-Peucker over the (t → (x, y)) path: any keyframe whose
    position is within ``tolerance_px`` of the line between its
    neighbours is redundant, because playback interpolates linearly
    anyway. Auto-tracking samples densely (several points per second);
    this collapses straight runs so the compiled drawtext expression
    stays short.
    """
    kfs = normalize_keyframes(keyframes)
    if len(kfs) <= 2:
        return kfs

    def deviation(kf, a, b):
        span = b["t"] - a["t"]
        frac = 0.0 if span <= 0 else (kf["t"] - a["t"]) / span
        lx = a["x"] + (b["x"] - a["x"]) * frac
        ly = a["y"] + (b["y"] - a["y"]) * frac
        return ((kf["x"] - lx) ** 2 + (kf["y"] - ly) ** 2) ** 0.5

    def rdp(points):
        if len(points) <= 2:
            return points
        a, b = points[0], points[-1]
        worst_i, worst_d = 0, -1.0
        for i in range(1, len(points) - 1):
            d = deviation(points[i], a, b)
            if d > worst_d:
                worst_i, worst_d = i, d
        if worst_d <= tolerance_px:
            return [a, b]
        left = rdp(points[: worst_i + 1])
        right = rdp(points[worst_i:])
        return left[:-1] + right

    return rdp(kfs)


def compile_axis_expr(keyframes, axis, escape_commas=True):
    """Compile one axis of the path into an ffmpeg drawtext expression.

    Emits nested ``if(lt(t,T),...)`` piecewise-linear segments with the
    same clamp-outside semantics as :func:`position_at`. Values are
    formatted with fixed precision so the string is deterministic.

    With ``escape_commas`` (the default) commas come out as ``\\,`` —
    ready to drop inside a single-quoted drawtext option value, matching
    the convention the ``enable=`` builder already uses.
    """
    kfs = normalize_keyframes(keyframes)
    if not kfs:
        return None
    key = "x" if axis == "x" else "y"

    def num(v):
        return f"{v:.4f}".rstrip("0").rstrip(".")

    if len(kfs) == 1:
        expr = num(kfs[0][key])
    else:
        # Innermost: clamp past the final keyframe.
        expr = num(kfs[-1][key])
        # Build segments from last to first so nesting reads in time order.
        for a, b in reversed(list(zip(kfs, kfs[1:]))):
            span = b["t"] - a["t"]
            slope = 0.0 if span <= 0 else (b[key] - a[key]) / span
            seg = f"{num(a[key])}+{num(slope)}*(t-{num(a['t'])})"
            expr = f"if(lt(t,{num(b['t'])}),{seg},{expr})"
        # Outermost: clamp before the first keyframe.
        expr = f"if(lt(t,{num(kfs[0]['t'])}),{num(kfs[0][key])},{expr})"

    if escape_commas:
        expr = expr.replace(",", "\\,")
    return expr
