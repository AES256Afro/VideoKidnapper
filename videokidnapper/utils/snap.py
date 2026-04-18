# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Figma-style snap math for dragging text layers on the preview.

This module is pure — no Tk, no Pillow — so the snapping behavior is
unit-testable and the VideoPlayer widget can stay focused on canvas
rendering + input dispatch.

Coordinate space: everything here is source-video pixels (the same
space drawtext's ``x:y`` expression uses at export time). The caller
(VideoPlayer) is responsible for mapping canvas coords in/out.
"""

from collections import namedtuple


# A single 1-D snap target. ``axis`` is ``"x"`` or ``"y"``.
# ``kind`` is the target edge on the DRAGGED layer that should meet
# ``value``: ``"start"`` (left/top edge), ``"center"``, or ``"end"``.
# ``label`` is an opaque token that identifies what we snapped to
# (e.g. ``"frame:center"``, ``"layer:2:right"``) — the widget uses it
# to decide where to draw the guide line.
SnapTarget = namedtuple("SnapTarget", "axis value kind label")


# A "snap result" entry — what the caller needs to actually render a guide.
SnapHit = namedtuple("SnapHit", "axis position label")


def build_targets(frame_w, frame_h, other_bboxes, edge_pad=20):
    """Return the full list of snap targets for a drag session.

    Parameters
    ----------
    frame_w, frame_h : int
        Source-video frame dimensions in pixels.
    other_bboxes : iterable of (idx, x1, y1, x2, y2)
        Bounding boxes of OTHER text layers (exclude the one being
        dragged). Coordinates in source-pixel space.
    edge_pad : int
        Margin from the frame edge that counts as a "soft edge" snap
        target — matches the preview's drawtext pad so a drag snaps
        the text to the same position a Top-Left preset would pick.
    """
    targets = []

    # Frame-relative guides: center lines and padded edges.
    targets.append(SnapTarget("x", frame_w / 2, "center", "frame:center"))
    targets.append(SnapTarget("y", frame_h / 2, "center", "frame:center"))
    targets.append(SnapTarget("x", edge_pad, "start", "frame:left"))
    targets.append(SnapTarget("y", edge_pad, "start", "frame:top"))
    targets.append(SnapTarget("x", frame_w - edge_pad, "end", "frame:right"))
    targets.append(SnapTarget("y", frame_h - edge_pad, "end", "frame:bottom"))

    # Peer-layer guides: align edges + centers with every other layer.
    for idx, x1, y1, x2, y2 in other_bboxes:
        cx = (x1 + x2) / 2
        cy = (y1 + y2) / 2
        targets.append(SnapTarget("x", x1, "start",  f"layer:{idx}:left"))
        targets.append(SnapTarget("x", x2, "end",    f"layer:{idx}:right"))
        targets.append(SnapTarget("x", cx, "center", f"layer:{idx}:centerx"))
        targets.append(SnapTarget("y", y1, "start",  f"layer:{idx}:top"))
        targets.append(SnapTarget("y", y2, "end",    f"layer:{idx}:bottom"))
        targets.append(SnapTarget("y", cy, "center", f"layer:{idx}:centery"))

    return targets


def _candidate_positions(value, kind, tw, th, axis):
    """Return the ``new_start`` value the dragged layer would need so
    that its ``kind`` edge lands on ``value`` for the given axis."""
    size = tw if axis == "x" else th
    if kind == "start":
        return value
    if kind == "end":
        return value - size
    # kind == "center"
    return value - size / 2


def apply_snap(new_x, new_y, tw, th, targets, threshold=8):
    """Snap ``(new_x, new_y)`` to the closest target within ``threshold``.

    ``(new_x, new_y)`` is the top-left corner of the dragged layer's
    bbox in source-pixel space; ``(tw, th)`` is its size. For each
    axis we pick the target that produces the smallest displacement,
    provided it's within ``threshold`` pixels. Axes are independent —
    a drag can snap horizontally without also snapping vertically.

    Returns ``(snapped_x, snapped_y, hits)`` where ``hits`` is a list
    of zero, one, or two ``SnapHit`` entries describing the guides
    the caller should draw.
    """
    best_x = None  # (distance, new_start, label, target_value)
    best_y = None

    for t in targets:
        new_start = _candidate_positions(t.value, t.kind, tw, th, t.axis)
        if t.axis == "x":
            dist = abs(new_start - new_x)
            if dist <= threshold and (best_x is None or dist < best_x[0]):
                best_x = (dist, new_start, t.label, t.value)
        else:
            dist = abs(new_start - new_y)
            if dist <= threshold and (best_y is None or dist < best_y[0]):
                best_y = (dist, new_start, t.label, t.value)

    snapped_x = best_x[1] if best_x else new_x
    snapped_y = best_y[1] if best_y else new_y

    hits = []
    if best_x:
        hits.append(SnapHit("x", best_x[3], best_x[2]))
    if best_y:
        hits.append(SnapHit("y", best_y[3], best_y[2]))

    return int(round(snapped_x)), int(round(snapped_y)), hits
