from snapit.core.ffmpeg_backend import extract_frame

_cache = {}


def get_frame_at(video_path, timestamp_seconds, cache_key=None):
    key = cache_key or (str(video_path), round(timestamp_seconds, 2))
    if key in _cache:
        return _cache[key]
    frame = extract_frame(video_path, timestamp_seconds)
    if frame:
        _cache[key] = frame
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
    _cache.clear()
