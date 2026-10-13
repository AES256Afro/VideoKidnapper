# SPDX-FileCopyrightText: 2026 AES256Afro <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Frame preview helpers.

The LRU cache is capped so long sessions don't balloon memory. ffmpeg
extraction is slow enough that even a small cache is hugely beneficial for
scrubbing; bumping `_MAX_ENTRIES` trades RAM for responsiveness.

It is capped twice: by count and by the memory the decoded frames take.
A count alone was 240 full frames, about 1.5 GB for 1080p video and 6 GB
for 4K.
"""

import os
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from threading import Lock

from videokidnapper.core.ffmpeg_backend import extract_frame


_MAX_ENTRIES = 240
_MAX_BYTES = 640 * 1024 * 1024
_cache: "OrderedDict[object, object]" = OrderedDict()
_sizes: "dict[object, int]" = {}
_bytes = 0
_lock = Lock()

# Thumbnails are fetched a few at a time: each is its own ffmpeg run
# (start-up plus a seek), so running them side by side cuts the wait
# for a filmstrip several times over without flooding the machine.
_THUMB_WORKERS = max(1, min(4, os.cpu_count() or 1))


def _frame_bytes(frame):
    """Memory a decoded frame takes; 0 for anything that is not an image."""
    try:
        w, h = frame.size
        return w * h * len(frame.getbands())
    except (AttributeError, TypeError, ValueError):
        return 0


def _cache_get(key):
    with _lock:
        if key in _cache:
            _cache.move_to_end(key)
            return _cache[key]
    return None


def _cache_put(key, value):
    global _bytes
    with _lock:
        if key in _cache:
            _bytes -= _sizes.pop(key, 0)
        _cache[key] = value
        _cache.move_to_end(key)
        _sizes[key] = _frame_bytes(value)
        _bytes += _sizes[key]
        # Always keep the newest entry, even if it alone is over budget.
        while len(_cache) > 1 and (len(_cache) > _MAX_ENTRIES or _bytes > _MAX_BYTES):
            old, _value = _cache.popitem(last=False)
            _bytes -= _sizes.pop(old, 0)


def get_frame_at(video_path, timestamp_seconds, cache_key=None, max_height=None):
    """The frame at ``timestamp_seconds``, from the cache when possible.

    ``max_height`` asks ffmpeg for a smaller frame, which is much cheaper
    to decode, keep and resize when only a thumbnail is needed.
    """
    key = cache_key or (str(video_path), round(timestamp_seconds, 2), max_height)
    cached = _cache_get(key)
    if cached is not None:
        return cached
    if max_height:
        frame = extract_frame(video_path, timestamp_seconds, max_height=max_height)
    else:
        frame = extract_frame(video_path, timestamp_seconds)
    if frame:
        if max_height:
            # Decode now, on the worker thread, rather than on first use.
            try:
                frame.load()
            except Exception:
                return None
        _cache_put(key, frame)
    return frame


def peek_frame(video_path, timestamp_seconds):
    """The cached full frame at ``timestamp_seconds``, or None. Never runs ffmpeg."""
    return _cache_get((str(video_path), round(timestamp_seconds, 2), None))


def extract_thumbnail_strip(video_path, duration, count=10, height=None):
    """``count`` frames spread evenly over ``duration``, in order.

    ``height`` fetches each frame at about that height (the filmstrip's
    lane), instead of at full size.
    """
    if duration <= 0 or count <= 0:
        return []
    interval = duration / count

    def one(i):
        ts = interval * i + interval / 2
        # The cache key must encode the duration/count the timestamp was
        # derived from — otherwise a strip regenerated for a different trim
        # range returns the previous range's stale thumbnails.
        key = (str(video_path), f"thumb_{count}_{round(duration, 2)}_{height}_{i}")
        try:
            return get_frame_at(video_path, ts, cache_key=key, max_height=height)
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=_THUMB_WORKERS) as pool:
        frames = list(pool.map(one, range(count)))
    return [frame for frame in frames if frame]


def clear_cache():
    global _bytes
    with _lock:
        _cache.clear()
        _sizes.clear()
        _bytes = 0


def cache_size():
    with _lock:
        return len(_cache)


def cache_bytes():
    with _lock:
        return _bytes
