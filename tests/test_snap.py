# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
from videokidnapper.utils.snap import apply_snap, build_targets


def test_frame_center_snap_horizontal():
    # 1920x1080 frame, 200x60 text. Dragging so its center is ~5px left
    # of frame center → should snap to exact center.
    targets = build_targets(1920, 1080, other_bboxes=[])
    # Text center at x=955 means new_x = 855; frame center target is 960,
    # center kind → candidate = 960 - 200/2 = 860. Distance 5 → within default 8.
    x, y, hits = apply_snap(855, 400, 200, 60, targets, threshold=8)
    assert x == 860
    assert any(h.label == "frame:center" and h.axis == "x" for h in hits)


def test_no_snap_outside_threshold():
    targets = build_targets(1920, 1080, other_bboxes=[])
    # Text center at x=900 → 60 pixels off frame center → too far to snap.
    x, y, hits = apply_snap(800, 400, 200, 60, targets, threshold=8)
    assert x == 800
    assert not any(h.axis == "x" for h in hits)


def test_edge_pad_snaps_left():
    targets = build_targets(1920, 1080, other_bboxes=[], edge_pad=20)
    # Drag close to left pad — should snap to x=20.
    x, y, hits = apply_snap(22, 500, 100, 30, targets, threshold=8)
    assert x == 20
    assert any(h.label == "frame:left" for h in hits)


def test_edge_pad_snaps_right():
    targets = build_targets(1920, 1080, other_bboxes=[], edge_pad=20)
    # Right edge target is at 1920-20=1900; "end" kind means new_x = 1900 - tw.
    tw = 100
    # Dragged to 1800 → naive right edge = 1900, snap candidate 1800.
    # Now drag to 1797 (right edge 1897, 3 off target) → should snap.
    x, y, hits = apply_snap(1797, 500, tw, 30, targets, threshold=8)
    assert x == 1800
    assert any(h.label == "frame:right" for h in hits)


def test_both_axes_snap_independently():
    targets = build_targets(1920, 1080, other_bboxes=[])
    # x snaps to frame center, y does not snap.
    x, y, hits = apply_snap(858, 17, 200, 60, targets, threshold=8)
    assert x == 860
    # y=17 is within 3 of edge pad 20 → should snap on y too.
    assert y == 20
    axes = sorted(h.axis for h in hits)
    assert axes == ["x", "y"]


def test_peer_layer_left_edge_alignment():
    # Two other layers; dragged layer should snap to align its left edge
    # with the leftmost peer.
    others = [
        (0, 500, 100, 700, 160),   # layer 0: left=500
        (1, 900, 200, 1100, 260),  # layer 1: left=900
    ]
    targets = build_targets(1920, 1080, other_bboxes=others)
    x, y, hits = apply_snap(503, 400, 150, 40, targets, threshold=8)
    assert x == 500
    assert any(h.label == "layer:0:left" for h in hits)


def test_closest_target_wins_when_two_in_range():
    # Frame center (960) "center" kind for a 100-wide text gives candidate 910.
    # Peer left edge 915 gives candidate 915. Dragging to 912 → both within
    # threshold; 910 is 2 off, 915 is 3 off → frame:center wins.
    others = [(0, 915, 100, 1015, 160)]
    targets = build_targets(1920, 1080, other_bboxes=others)
    x, _, hits = apply_snap(912, 400, 100, 40, targets, threshold=8)
    assert x == 910
    assert any(h.label == "frame:center" for h in hits)


def test_exclusion_of_dragged_layer_is_callers_job():
    # build_targets makes no assumption; the caller (VideoPlayer) must
    # filter the dragged index out before calling. This test pins that
    # contract: a self-bbox in `other_bboxes` does produce targets.
    targets = build_targets(1920, 1080, other_bboxes=[(0, 100, 100, 200, 140)])
    labels = {t.label for t in targets}
    assert "layer:0:left" in labels
