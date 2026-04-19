# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0

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


def test_schema_v3_upgrades_to_v4(fresh_settings, tmp_path):
    # A v3 settings file (pre-batch-persistence) must pick up the new
    # batch_jobs default without clobbering any of the user's existing
    # settings, and must bump _version to 4.
    import json
    fresh_settings._SETTINGS_PATH.write_text(
        json.dumps({
            "_version": 3,
            "quality": "High",
            "color_brightness": 0.1,
        }),
        encoding="utf-8",
    )
    # Force a re-read by clearing any cached state.
    assert fresh_settings.get("batch_jobs") == []
    assert fresh_settings.get("quality") == "High"
    assert fresh_settings.get("color_brightness") == 0.1
    # Touching any key rewrites the file; verify the version bumped.
    fresh_settings.set("quality", "Ultra")
    saved = json.loads(fresh_settings._SETTINGS_PATH.read_text(encoding="utf-8"))
    assert saved["_version"] == 4
    assert saved["batch_jobs"] == []


def test_batch_jobs_round_trip(fresh_settings):
    fresh_settings.set("batch_jobs", [
        {"input_path": "/a.mp4", "output_path": "/b.mp4", "status": "queued"},
    ])
    restored = fresh_settings.get("batch_jobs")
    assert isinstance(restored, list)
    assert len(restored) == 1
    assert restored[0]["input_path"] == "/a.mp4"
