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
