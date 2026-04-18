import pytest


@pytest.fixture
def fresh_settings(tmp_path, monkeypatch):
    from videokidnapper.utils import settings
    monkeypatch.setattr(settings, "_SETTINGS_PATH", tmp_path / "s.json")
    return settings


def test_history_empty_by_default(fresh_settings):
    assert fresh_settings.get_history() == []


def test_history_adds_and_returns_newest_first(fresh_settings):
    fresh_settings.add_history_entry({"path": "/a", "format": "GIF"})
    fresh_settings.add_history_entry({"path": "/b", "format": "MP4"})
    history = fresh_settings.get_history()
    assert history[0]["path"] == "/b"
    assert history[1]["path"] == "/a"


def test_history_capped_at_25(fresh_settings):
    for i in range(40):
        fresh_settings.add_history_entry({"path": f"/{i}"})
    assert len(fresh_settings.get_history()) == 25


def test_clear_history(fresh_settings):
    fresh_settings.add_history_entry({"path": "/a"})
    fresh_settings.clear_history()
    assert fresh_settings.get_history() == []


def test_migration_adds_missing_keys(fresh_settings, tmp_path):
    # Pre-seed a v1 settings file without the new keys.
    import json
    (fresh_settings._SETTINGS_PATH).write_text(json.dumps({
        "_version": 1, "quality": "High",
    }))
    assert fresh_settings.get("theme") == "dark"
    assert fresh_settings.get("aspect_preset") == "Source"
    assert fresh_settings.get("history") == []
    assert fresh_settings.get("quality") == "High"  # preserved
