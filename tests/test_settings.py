import importlib

import pytest


@pytest.fixture
def fresh_settings(tmp_path, monkeypatch):
    from videokidnapper.utils import settings
    monkeypatch.setattr(settings, "_SETTINGS_PATH", tmp_path / "s.json")
    return settings


def test_defaults_returned_when_missing(fresh_settings):
    assert fresh_settings.get("quality") == "Medium"
    assert fresh_settings.get("format") == "GIF"


def test_set_and_get(fresh_settings):
    fresh_settings.set("quality", "High")
    assert fresh_settings.get("quality") == "High"


def test_update_merges(fresh_settings):
    fresh_settings.update({"quality": "Ultra", "rotate": 90})
    assert fresh_settings.get("quality") == "Ultra"
    assert fresh_settings.get("rotate") == 90


def test_unknown_key_returns_default_parameter(fresh_settings):
    assert fresh_settings.get("unknown_key", "fallback") == "fallback"


def test_reset_clears(fresh_settings):
    fresh_settings.set("quality", "High")
    fresh_settings.reset()
    assert fresh_settings.get("quality") == "Medium"


def test_corrupt_file_returns_defaults(fresh_settings):
    fresh_settings._SETTINGS_PATH.write_text("{not valid json")
    assert fresh_settings.get("quality") == "Medium"
