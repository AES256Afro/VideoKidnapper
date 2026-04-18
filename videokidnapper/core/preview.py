# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Frame preview helpers.

The LRU cache is capped so long sessions don't balloon memory. ffmpeg
extraction is slow enough that even a small cache is hugely beneficial for
scrubbing; bumping `_MAX_ENTRIES` trades RAM for responsiveness.
"""

from collections import OrderedDict
from threading import Lock

from videokidnapper.core.ffmpeg_backend import extract_frame


_MAX_ENTRIES = 240
_cache: "OrderedDict[object, object]" = OrderedDict()
_lock = Lock()


def _cache_get(key):
    with _lock:
        if key in _cache:
            _cache.move_to_end(key)
            return _cache[key]
    return None


def _cache_put(key, value):
    with _lock:
        _cache[key] = value
        _cache.move_to_end(key)
        while len(_cache) > _MAX_ENTRIES:
            _cache.popitem(last=False)


def get_frame_at(video_path, timestamp_seconds, cache_key=None):
    key = cache_key or (str(video_path), round(timestamp_seconds, 2))
    cached = _cache_get(key)
    if cached is not None:
        return cached
    frame = extract_frame(video_path, timestamp_seconds)
    if frame:
        _cache_put(key, frame)
    return frame


def extract_thumbnail_strip(video_path, duration, count=10):
    if duration <= 0 or count <= 0:
        return []
    interval = duration / count
    thumbnails = []
    for i in range(count):
        ts = interval * i + interval / 2
        frame = get_frame_at(video_path, ts, cache_key=(str(video_path), f"thumb_{i}"))
        if frame:
            thumbnails.append(frame)
    return thumbnails


def clear_cache():
    with _lock:
        _cache.clear()


def cache_size():
    with _lock:
        return len(_cache)
