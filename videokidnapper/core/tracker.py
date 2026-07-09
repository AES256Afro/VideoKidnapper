# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Auto-tracking for motion captions: follow a region through the video.

Optional feature gated on OpenCV (``pip install opencv-contrib-python``),
the same soft-dependency pattern as faster-whisper. The tracker follows
the patch of video under the caption and emits keyframes in the format
``utils.keyframes`` consumes, so auto-tracked and hand-dragged paths are
the same thing downstream.
"""

from videokidnapper.utils.keyframes import normalize_keyframes, simplify_keyframes

# Track on frames at most this wide — CSRT is O(pixels) and meme sources
# are often 1080p+; coordinates are scaled back to source space.
_TRACK_MAX_WIDTH = 640


def tracking_available():
    """(ok, hint) — is OpenCV with the CSRT tracker importable?"""
    try:
        cv2 = _cv2()
        _make_tracker(cv2)
        return True, ""
    except Exception:
        return False, (
            "Auto-track needs OpenCV. Install with: "
            "pip install opencv-contrib-python"
        )


def _cv2():
    import cv2
    return cv2


def _make_tracker(cv2):
    """CSRT if available (contrib), else KCF, else MIL — accuracy order."""
    for name in ("TrackerCSRT", "TrackerKCF", "TrackerMIL"):
        factory = getattr(cv2, name, None)
        if factory is not None and hasattr(factory, "create"):
            return factory.create()
        legacy = getattr(getattr(cv2, "legacy", None), f"{name}_create", None)
        if legacy is not None:
            return legacy()
    raise RuntimeError("no OpenCV tracker implementation found")


def track_region(video_path, bbox, start_t, end_t,
                 samples_per_second=6, simplify_px=3.0,
                 progress_cb=None, cancel_event=None):
    """Track ``bbox`` (source-pixel x, y, w, h) from ``start_t`` to ``end_t``.

    Returns simplified keyframes ``[{"t", "x", "y"}, ...]`` where x/y is
    the tracked region's top-left per sampled time — the caller applies
    whatever offset maps region → caption position. Raises RuntimeError
    on unusable input; returns at least the initial keyframe otherwise
    (if the tracker loses the target midway, the path simply ends at the
    last confident point).
    """
    cv2 = _cv2()

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"could not open video: {video_path}")
    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        src_w = cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0
        if src_w <= 0:
            raise RuntimeError("video reports no width")
        scale = min(1.0, _TRACK_MAX_WIDTH / src_w)

        cap.set(cv2.CAP_PROP_POS_MSEC, max(0.0, start_t) * 1000.0)
        ok, frame = cap.read()
        if not ok:
            raise RuntimeError("could not read the first frame at start time")

        def shrink(f):
            if scale >= 1.0:
                return f
            return cv2.resize(f, (0, 0), fx=scale, fy=scale,
                              interpolation=cv2.INTER_AREA)

        x, y, w, h = (int(v * scale) for v in bbox)
        small = shrink(frame)
        fh, fw = small.shape[:2]
        # Clamp the box inside the frame; a sliver of a box can't track.
        x = max(0, min(x, fw - 4))
        y = max(0, min(y, fh - 4))
        w = max(8, min(w, fw - x))
        h = max(8, min(h, fh - y))

        tracker = _make_tracker(cv2)
        tracker.init(small, (x, y, w, h))

        inv = 1.0 / scale
        keyframes = [{"t": float(start_t), "x": x * inv, "y": y * inv}]
        span = max(0.001, end_t - start_t)
        sample_every = max(1, int(round(fps / max(1, samples_per_second))))

        frame_i = 0
        t = float(start_t)
        while t < end_t:
            if cancel_event is not None and cancel_event.is_set():
                break
            ok, frame = cap.read()
            if not ok:
                break
            frame_i += 1
            t = start_t + frame_i / fps
            ok, box = tracker.update(shrink(frame))
            if not ok:
                break                      # target lost: end the path here
            if frame_i % sample_every == 0 or t >= end_t:
                keyframes.append(
                    {"t": t, "x": box[0] * inv, "y": box[1] * inv})
            if progress_cb and frame_i % 10 == 0:
                progress_cb(min(1.0, (t - start_t) / span))
    finally:
        cap.release()

    if progress_cb:
        progress_cb(1.0)
    return simplify_keyframes(normalize_keyframes(keyframes),
                              tolerance_px=simplify_px)
