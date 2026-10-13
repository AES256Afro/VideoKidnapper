# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Opening, saving and recovering projects never loses or overwrites work.

The TrimTab methods run against a small stand-in for the editor, so no
window is created; the file handling underneath is the real code.
"""

import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from videokidnapper.ui import trim_tab as trim_tab_module
from videokidnapper.ui.editor_options import _choice, _rotate_label
from videokidnapper.ui.project_dialog import RecoveryDialog
from videokidnapper.ui.trim_tab import TrimTab
from videokidnapper.utils import project_files


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(project_files.settings, "_SETTINGS_PATH", tmp_path / "settings.json")
    monkeypatch.setattr(trim_tab_module.settings, "add_recent_project", lambda path: None)


class _Var:
    def __init__(self, value=""):
        self.value = value

    def set(self, value):
        self.value = value

    def get(self):
        return self.value


def _editor(video="clip.mp4", fail_on_options=False):
    """Enough of a TrimTab for the project methods."""
    notes = []
    editor = SimpleNamespace(
        video_path=video, current_project_path=None, _project_dirty=False,
        _recovery_pending=False, _restoring=False, _autosave_after_id=None,
        platform_var=_Var(), quality_var=_Var(), format_var=_Var(),
        notes=notes,
    )

    def apply_options(options):
        if fail_on_options:
            raise ValueError("bad option")

    editor.export_options = SimpleNamespace(
        apply_options=apply_options, get_options=lambda: {},
        get_output_folder=lambda: "",
    )
    editor._notify = lambda message, kind="info": notes.append((kind, message))
    editor._load_path = lambda path, preserve_project=False: True
    editor._apply_snapshot = lambda state: None
    editor._snapshot = lambda: {"range": [0.0, 1.0], "queued": [], "layers": [], "images": []}
    editor._project_export_state = lambda: {}
    editor._undo_stack = SimpleNamespace(reset=lambda state: None)
    editor._update_project_status = lambda: None
    editor._flush_pending_snapshot = lambda: None
    editor._emit_state = lambda: None
    editor.player = SimpleNamespace(refresh_overlay=lambda: None)
    editor._prepare_to_replace_project = lambda: True
    for name in ("_project_document", "_write_autosave", "save_project",
                 "open_project", "request_close", "discard_recovery",
                 "postpone_recovery"):
        setattr(editor, name, getattr(TrimTab, name).__get__(editor))
    return editor


def _write_project(path, source, **changes):
    document = project_files.build_document(
        source, {"range": [0, 1], "queued": [], "layers": [], "images": []}, {}, path)
    document.update(changes)
    return project_files.save_document(path, document)


@pytest.fixture
def video(tmp_path):
    path = tmp_path / "clip.mp4"
    path.write_bytes(b"video")
    return path


# -- recovering an untitled autosave -------------------------------------------

def test_recovered_untitled_work_is_saved_somewhere_new(video, monkeypatch):
    autosave = _write_project(project_files.autosave_path(), video, linked_project_path="")
    editor = _editor(str(video))
    assert editor.open_project(autosave, recovery=True)
    assert editor.current_project_path is None
    assert editor._project_dirty

    asked = []
    monkeypatch.setattr(trim_tab_module.filedialog, "asksaveasfilename",
                        lambda **kw: asked.append(kw) or "")
    assert editor.save_project() is False
    assert asked, "Save must ask where to save, not write into the autosave"
    assert project_files.autosave_path().is_file()


def test_save_never_targets_the_autosave(video, monkeypatch):
    editor = _editor(str(video))
    editor.current_project_path = str(project_files.autosave_path())
    monkeypatch.setattr(trim_tab_module.filedialog, "asksaveasfilename", lambda **kw: "")
    assert editor.save_project() is False


def test_closing_during_the_recovery_prompt_keeps_the_autosave(video):
    _write_project(project_files.autosave_path(), video)
    editor = _editor(str(video))
    editor._recovery_pending = True
    assert editor.request_close() is True
    assert project_files.autosave_path().is_file()


def test_closing_the_prompt_postpones_instead_of_discarding(video):
    _write_project(project_files.autosave_path(), video)
    editor = _editor(str(video))
    dialog = SimpleNamespace(editor=editor, path=project_files.autosave_path(),
                             destroy=lambda: None)
    RecoveryDialog._later(dialog)
    assert not project_files.autosave_path().exists()
    assert project_files.postponed_autosave_path().is_file()
    assert project_files.recoverable_autosave() == project_files.postponed_autosave_path()
    assert not editor._recovery_pending


def test_recovering_a_postponed_autosave_moves_it_back(video):
    postponed = _write_project(project_files.postponed_autosave_path(), video)
    editor = _editor(str(video))
    assert editor.open_project(postponed, recovery=True)
    assert project_files.autosave_path().is_file()
    assert not postponed.exists()


def test_fresh_autosave_is_offered_before_a_postponed_one(video):
    _write_project(project_files.postponed_autosave_path(), video)
    _write_project(project_files.autosave_path(), video)
    assert project_files.recoverable_autosave() == project_files.autosave_path()


# -- a damaged project never overwrites the open one -----------------------------

def test_damaged_project_opens_untitled(tmp_path, video):
    a = _write_project(tmp_path / "A.vidkid", video)
    b = _write_project(tmp_path / "B.vidkid", video)
    editor = _editor(str(video), fail_on_options=True)
    editor.current_project_path = str(a)
    a_before = a.read_text(encoding="utf-8")

    assert editor.open_project(b)
    assert editor.current_project_path is None, "a save would overwrite A.vidkid"
    assert editor._project_dirty
    assert editor.notes[-1][0] == "warn"
    assert a.read_text(encoding="utf-8") == a_before


@pytest.mark.parametrize("content", [
    b"\xff\xfe not text",
    json.dumps({"schema_version": 1, "editor": {"range": [0, 1]},
                "source": {"path": 5}}).encode(),
    json.dumps({"schema_version": 1, "editor": {"range": [0, 1], "images": [{"path": 3}]},
                "source": {"path": "x.mp4"}}).encode(),
    json.dumps({"schema_version": 1, "editor": {"range": [0, 1]},
                "source": {"path": "x.mp4"}, "linked_project_path": ["x"]}).encode(),
])
def test_unreadable_projects_are_project_errors(tmp_path, content):
    path = tmp_path / "bad.vidkid"
    path.write_bytes(content)
    with pytest.raises(project_files.ProjectFileError):
        project_files.load_document(path)


# -- a moved project finds its media ---------------------------------------------

def test_moved_project_folder_finds_its_media(tmp_path):
    folder = tmp_path / "alice" / "edit"
    folder.mkdir(parents=True)
    (folder / "clip.mp4").write_bytes(b"v")
    (folder / "logo.png").write_bytes(b"i")
    document = project_files.build_document(
        folder / "clip.mp4",
        {"range": [0, 1], "queued": [], "layers": [],
         "images": [{"path": str(folder / "logo.png")}]},
        {}, folder / "edit.vidkid")
    project_files.save_document(folder / "edit.vidkid", document)

    moved = tmp_path / "bob" / "received" / "edit"
    moved.parent.mkdir(parents=True)
    shutil.move(str(folder), str(moved))
    loaded = project_files.load_document(moved / "edit.vidkid")
    assert Path(loaded["resolved_source"]) == (moved / "clip.mp4").resolve()
    assert Path(loaded["editor"]["images"][0]["path"]) == (moved / "logo.png").resolve()


# -- option values from files ----------------------------------------------------

def test_option_lookups_tolerate_any_json():
    assert _choice({0: "Forever"}, [1], "Forever") == "Forever"
    assert _choice({0: "Forever"}, {"a": 1}, "x") == "x"
    assert _rotate_label("90deg") == "0°"
    assert _rotate_label(450) == "90°"
    assert _rotate_label(None) == "0°"
    assert _rotate_label(45) == "0°"
