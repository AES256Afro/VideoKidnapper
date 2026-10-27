# SPDX-FileCopyrightText: 2026 AES256Afro <https://github.com/AES256Afro>
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


def test_first_run_tracks_settings_file(fresh_settings):
    assert fresh_settings.is_first_run() is True
    fresh_settings.set("onboarding_complete", True)
    assert fresh_settings.is_first_run() is False


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
    # Touching any key rewrites the file; verify the version bumped to
    # whatever the current schema is (writes always stamp _CURRENT_SCHEMA).
    fresh_settings.set("quality", "Ultra")
    saved = json.loads(fresh_settings._SETTINGS_PATH.read_text(encoding="utf-8"))
    assert saved["_version"] == fresh_settings._CURRENT_SCHEMA
    assert saved["batch_jobs"] == []


def test_schema_v4_upgrades_to_v5(fresh_settings):
    # A v4 settings file (pre-GIF-options) must pick up the new GIF
    # defaults (matching the previously-hardcoded pipeline values)
    # without clobbering existing settings.
    import json
    fresh_settings._SETTINGS_PATH.write_text(
        json.dumps({
            "_version": 4,
            "quality": "High",
            "batch_jobs": [],
        }),
        encoding="utf-8",
    )
    assert fresh_settings.get("gif_dither") == "bayer"
    assert fresh_settings.get("gif_stats_mode") == "full"
    assert fresh_settings.get("gif_loop") == 0
    assert fresh_settings.get("quality") == "High"
    fresh_settings.set("quality", "Ultra")
    saved = json.loads(fresh_settings._SETTINGS_PATH.read_text(encoding="utf-8"))
    assert saved["_version"] == fresh_settings._CURRENT_SCHEMA
    assert saved["gif_dither"] == "bayer"


def test_schema_v5_upgrades_to_current(fresh_settings):
    # A v5 settings file (pre-aspect-fill-mode) must pick up the "crop"
    # default, which reproduces the historical center-crop behavior.
    import json
    fresh_settings._SETTINGS_PATH.write_text(
        json.dumps({
            "_version": 5,
            "quality": "High",
            "gif_dither": "none",
        }),
        encoding="utf-8",
    )
    assert fresh_settings.get("aspect_fill_mode") == "crop"
    assert fresh_settings.get("gif_dither") == "none"
    fresh_settings.set("quality", "Ultra")
    saved = json.loads(fresh_settings._SETTINGS_PATH.read_text(encoding="utf-8"))
    assert saved["_version"] == fresh_settings._CURRENT_SCHEMA
    assert saved["aspect_fill_mode"] == "crop"


@pytest.mark.parametrize("stored,expected", [
    ("dark", "light"),      # the default before 1.8.2
    ("cream", "light"),     # the default from 1.8.2
    ("fallout", "fallout"),  # picked on purpose: kept
    ("retro", "retro"),
    ("light", "light"),
])
def test_schema_v8_moves_old_defaults_to_studio(fresh_settings, stored, expected):
    import json
    fresh_settings._SETTINGS_PATH.write_text(
        json.dumps({"_version": 7, "theme": stored}),
        encoding="utf-8",
    )
    assert fresh_settings.get("theme") == expected


def test_batch_jobs_round_trip(fresh_settings):
    fresh_settings.set("batch_jobs", [
        {"input_path": "/a.mp4", "output_path": "/b.mp4", "status": "queued"},
    ])
    restored = fresh_settings.get("batch_jobs")
    assert isinstance(restored, list)
    assert len(restored) == 1
    assert restored[0]["input_path"] == "/a.mp4"


def test_recent_projects_are_deduplicated_and_capped(fresh_settings, tmp_path):
    paths = []
    for index in range(10):
        path = tmp_path / f"{index}.vidkid"
        path.write_text("{}", encoding="utf-8")
        paths.append(path)
        fresh_settings.add_recent_project(path)
    fresh_settings.add_recent_project(paths[5])
    recent = fresh_settings.get_recent_projects()
    assert len(recent) == 8
    assert recent[0] == str(paths[5].resolve())
    assert len({item.lower() for item in recent}) == len(recent)


# -- hand-edited settings never stop the app ------------------------------------

@pytest.mark.parametrize("content", [
    b"\xff\xfe\x00 not utf-8",
    b'{"_version": "8", "quality": "High"}',
    b'{"_version": null, "quality": "High"}',
])
def test_odd_files_still_load(fresh_settings, content):
    fresh_settings._SETTINGS_PATH.write_bytes(content)
    assert fresh_settings.get("format") == "GIF"


@pytest.mark.parametrize("key,bad", [
    ("theme", ["dark"]), ("color_contrast", None), ("text_fade", "0.5"),
    ("gif_loop", [1]), ("recent_projects", 5), ("history", 5),
    ("mute_audio", "yes"), ("rotate", 90.5), ("speed", True),
])
def test_values_of_the_wrong_type_fall_back_to_defaults(fresh_settings, key, bad):
    import json
    fresh_settings._SETTINGS_PATH.write_text(
        json.dumps({"_version": 8, key: bad, "quality": "High"}), encoding="utf-8")
    assert fresh_settings.get(key) == fresh_settings._DEFAULTS[key]
    assert fresh_settings.get("quality") == "High"


def test_whole_numbers_are_fine_where_decimals_are_expected(fresh_settings):
    fresh_settings.set("speed", 2)
    fresh_settings.set("color_gamma", 1)
    assert fresh_settings.get("speed") == 2 and fresh_settings.get("color_gamma") == 1


def test_write_retries_while_another_reader_has_the_file(fresh_settings, monkeypatch):
    import os
    fresh_settings.set("quality", "Low")
    calls = {"n": 0}
    real_replace = os.replace

    def flaky(src, dst):
        calls["n"] += 1
        if calls["n"] < 3:
            raise PermissionError(13, "The process cannot access the file")
        return real_replace(src, dst)

    monkeypatch.setattr(fresh_settings.os, "replace", flaky)
    monkeypatch.setattr(fresh_settings, "_RETRY_DELAYS", (0, 0, 0, 0, 0))
    fresh_settings.set("quality", "Ultra")
    assert fresh_settings.get("quality") == "Ultra"
    assert calls["n"] == 3
