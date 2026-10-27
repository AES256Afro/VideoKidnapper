# SPDX-FileCopyrightText: 2026 AES256Afro <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
from videokidnapper.core import preview


def test_cache_is_capped(monkeypatch):
    monkeypatch.setattr(preview, "_MAX_ENTRIES", 5)
    preview.clear_cache()
    for i in range(20):
        preview._cache_put(("v", i), f"frame-{i}")
    assert preview.cache_size() == 5


def test_lru_evicts_oldest(monkeypatch):
    monkeypatch.setattr(preview, "_MAX_ENTRIES", 3)
    preview.clear_cache()
    preview._cache_put("a", 1)
    preview._cache_put("b", 2)
    preview._cache_put("c", 3)
    # Touch "a" so it becomes most-recently-used.
    assert preview._cache_get("a") == 1
    preview._cache_put("d", 4)
    # "b" should be the one evicted, not "a".
    assert preview._cache_get("b") is None
    assert preview._cache_get("a") == 1


def test_clear_empties_cache():
    preview._cache_put("x", 1)
    preview.clear_cache()
    assert preview.cache_size() == 0


class _Frame:
    """Stands in for a PIL image: only its size and bands matter here."""

    def __init__(self, w, h):
        self.size = (w, h)

    def getbands(self):
        return ("R", "G", "B")

    def load(self):
        pass


def test_cache_is_capped_by_memory(monkeypatch):
    monkeypatch.setattr(preview, "_MAX_BYTES", 3 * 100 * 100 * 3)
    preview.clear_cache()
    for i in range(10):
        preview._cache_put(("v", i), _Frame(100, 100))
    assert preview.cache_size() == 3
    assert preview.cache_bytes() == 3 * 100 * 100 * 3
    # One frame larger than the whole budget is still kept, alone.
    preview._cache_put("huge", _Frame(1000, 1000))
    assert preview.cache_size() == 1


def test_replacing_an_entry_does_not_double_count(monkeypatch):
    preview.clear_cache()
    preview._cache_put("a", _Frame(10, 10))
    preview._cache_put("a", _Frame(10, 10))
    assert preview.cache_bytes() == 300


def test_thumbnail_strip_is_small_ordered_and_cached(monkeypatch):
    preview.clear_cache()
    calls = []

    def fake_extract(path, ts, max_height=None):
        calls.append((round(ts, 3), max_height))
        frame = _Frame(int(max_height * 16 / 9), max_height)
        frame.ts = ts
        return frame

    monkeypatch.setattr(preview, "extract_frame", fake_extract)
    frames = preview.extract_thumbnail_strip("clip.mp4", 10.0, count=5, height=56)
    assert [round(f.ts, 1) for f in frames] == [1.0, 3.0, 5.0, 7.0, 9.0]
    assert all(h == 56 for _ts, h in calls)
    preview.extract_thumbnail_strip("clip.mp4", 10.0, count=5, height=56)
    assert len(calls) == 5, "a second strip comes from the cache"


def test_full_frames_are_decoded_before_anyone_else_can_see_them(monkeypatch):
    """A full frame was cached still undecoded, then decoded by the scrub
    worker and the Tk thread at once, which garbled it."""
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (32, 18), (200, 10, 10)).save(buf, "PNG")
    seen = []

    def extract(_path, _ts, **_kw):
        img = Image.open(io.BytesIO(buf.getvalue()))
        seen.append(img)
        return img

    monkeypatch.setattr(preview, "extract_frame", extract)
    preview.clear_cache()
    frame = preview.get_frame_at("clip.mp4", 1.0)
    # Decoded: the lazy file handle is gone and the pixels are in memory.
    assert frame is seen[0]
    assert getattr(frame, "fp", None) is None
    assert preview.peek_frame("clip.mp4", 1.0) is frame
    assert frame.getpixel((0, 0)) == (200, 10, 10)


def test_a_frame_that_will_not_decode_is_not_cached(monkeypatch):
    class Broken:
        size = (4, 4)

        def getbands(self):
            return ("R", "G", "B")

        def load(self):
            raise OSError("truncated")

    monkeypatch.setattr(preview, "extract_frame", lambda *_a, **_k: Broken())
    preview.clear_cache()
    assert preview.get_frame_at("clip.mp4", 2.0) is None
    assert preview.peek_frame("clip.mp4", 2.0) is None
