# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0

import json

import pytest

from videokidnapper.utils import project_files


def test_project_round_trip_resolves_relative_media(tmp_path):
    source = tmp_path / "media" / "clip.mp4"
    overlay = tmp_path / "media" / "logo.png"
    source.parent.mkdir()
    source.write_bytes(b"video")
    overlay.write_bytes(b"image")
    project_path = tmp_path / "work" / "demo.vidkid"

    document = project_files.build_document(
        source,
        {
            "range": [1.0, 2.0], "queued": [], "crop": None,
            "layers": [], "images": [{"path": str(overlay), "opacity": 0.5}],
        },
        {"format": "MP4", "quality": "High"},
        project_path,
    )
    saved = project_files.save_document(project_path, document)
    loaded = project_files.load_document(saved)

    assert loaded["resolved_source"] == str(source.resolve())
    assert loaded["editor"]["images"][0]["path"] == str(overlay.resolve())
    assert loaded["export"]["format"] == "MP4"


def test_project_save_adds_extension_and_is_valid_json(tmp_path):
    document = project_files.build_document(
        tmp_path / "clip.mp4",
        {"range": [0, 1], "queued": [], "layers": [], "images": []},
        {},
    )
    saved = project_files.save_document(tmp_path / "session", document)
    assert saved.suffix == ".vidkid"
    assert json.loads(saved.read_text(encoding="utf-8"))["schema_version"] == 1


def test_project_rejects_future_schema(tmp_path):
    path = tmp_path / "future.vidkid"
    path.write_text(json.dumps({
        "schema_version": 99,
        "source": {},
        "editor": {},
    }), encoding="utf-8")
    with pytest.raises(project_files.ProjectFileError, match="newer"):
        project_files.load_document(path)


def test_autosave_follows_isolated_settings_path(tmp_path, monkeypatch):
    monkeypatch.setattr(project_files.settings, "_SETTINGS_PATH", tmp_path / "settings.json")
    assert project_files.autosave_path() == tmp_path / project_files.AUTOSAVE_NAME


def test_autosave_resolves_paths_from_linked_project(tmp_path):
    source = tmp_path / "media" / "clip.mp4"
    source.parent.mkdir()
    source.write_bytes(b"video")
    intended = tmp_path / "projects" / "edit.vidkid"
    autosave = tmp_path / "recovery" / "autosave.vidkid"
    document = project_files.build_document(
        source,
        {"range": [0, 1], "queued": [], "layers": [], "images": []},
        {}, intended,
    )
    project_files.save_document(autosave, document)
    assert project_files.load_document(autosave)["resolved_source"] == str(source.resolve())


@pytest.mark.parametrize("bad_range", [None, [0], [0, "one"], [0, float("nan")]])
def test_project_rejects_invalid_ranges(tmp_path, bad_range):
    path = tmp_path / "bad.vidkid"
    path.write_text(json.dumps({
        "schema_version": 1,
        "source": {"path": str(tmp_path / "clip.mp4")},
        "editor": {"range": bad_range, "queued": [], "layers": [], "images": []},
        "export": {},
    }), encoding="utf-8")
    with pytest.raises(project_files.ProjectFileError, match="range"):
        project_files.load_document(path)
