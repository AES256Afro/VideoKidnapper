# SPDX-FileCopyrightText: 2026 AES256Afro <https://github.com/AES256Afro>
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
from videokidnapper.ui.studio.banner import PromptQueue
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
    """Enough of a TrimTab for the project methods.

    ``editor.app.banner`` is the banner's real queue, without widgets, so
    a test answers a prompt the way a click would.
    """
    notes = []
    editor = SimpleNamespace(
        video_path=video, current_project_path=None, _project_dirty=False,
        _recovery_pending=False, _recovery_path=None, _recovery_prompt=None,
        _restoring=False, _autosave_after_id=None,
        platform_var=_Var(), quality_var=_Var(), format_var=_Var(),
        notes=notes, app=SimpleNamespace(banner=PromptQueue()),
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
    for name in ("_project_document", "_write_autosave", "save_project",
                 "open_project", "_apply_project", "request_close",
                 "offer_recovery", "discard_recovery", "postpone_recovery",
                 "_set_aside_recovery", "_prepare_to_replace_project"):
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
    editor = _editor(None)
    editor.offer_recovery(project_files.autosave_path())
    closed = []
    editor.request_close(lambda: closed.append(True))
    assert closed == [True], "nothing to ask: the app closes at once"
    assert project_files.autosave_path().is_file()


def test_closing_the_prompt_postpones_instead_of_discarding(video):
    _write_project(project_files.autosave_path(), video)
    editor = _editor(None)
    prompt = editor.offer_recovery(project_files.autosave_path())
    assert prompt.showing and editor._recovery_pending
    assert prompt.dismiss(), "the ✕ means later"
    assert not project_files.autosave_path().exists()
    assert project_files.postponed_autosave_path().is_file()
    assert project_files.recoverable_autosave() == project_files.postponed_autosave_path()
    assert not editor._recovery_pending


def test_later_on_a_postponed_autosave_leaves_it_where_it_is(video):
    postponed = _write_project(project_files.postponed_autosave_path(), video)
    editor = _editor(None)
    editor.offer_recovery(postponed).dismiss()
    assert postponed.is_file()
    assert not editor._recovery_pending


def test_discard_deletes_the_offered_autosave(video):
    autosave = _write_project(project_files.autosave_path(), video)
    editor = _editor(None)
    prompt = editor.offer_recovery(autosave)
    prompt.press("Discard")
    assert not autosave.exists()
    assert not editor._recovery_pending
    assert editor.app.banner.current is None


def test_recover_opens_the_autosave_and_closes_the_prompt(video):
    autosave = _write_project(project_files.autosave_path(), video)
    editor = _editor(str(video))
    prompt = editor.offer_recovery(autosave)
    prompt.press("Recover")
    assert not prompt.is_open
    assert not editor._recovery_pending
    assert editor._project_dirty
    assert editor.notes[-1] == ("success", "Recovered autosaved project")


def test_a_failed_recovery_leaves_the_prompt_up():
    autosave = project_files.autosave_path()
    autosave.write_bytes(b"not a project")
    editor = _editor(None)
    prompt = editor.offer_recovery(autosave)
    prompt.press("Recover")
    assert prompt.showing, "Discard and later must still be possible"
    assert editor._recovery_pending
    assert autosave.is_file()


def test_opening_something_else_while_the_prompt_waits_is_later(tmp_path, video):
    """The prompt is no longer modal, so this can happen now. Opening a
    project deletes the autosave and new edits overwrite it: the offered
    work has to move aside first."""
    autosave = _write_project(project_files.autosave_path(), video)
    other = _write_project(tmp_path / "Other.vidkid", video)
    editor = _editor(None)
    prompt = editor.offer_recovery(autosave)

    assert editor.open_project(other)
    assert not prompt.is_open
    assert not editor._recovery_pending
    assert project_files.recoverable_autosave() == project_files.postponed_autosave_path()
    assert editor.current_project_path == str(other.resolve())


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


# -- unsaved work is asked about in the banner ------------------------------------

def _dirty_editor(video, tmp_path):
    """An editor with unsaved changes to a saved project, A.vidkid."""
    a = _write_project(tmp_path / "A.vidkid", video)
    editor = _editor(str(video))
    editor.current_project_path = str(a)
    editor._project_dirty = True
    return editor


def _answer(prompt, answer):
    return prompt.dismiss() if answer == "dismiss" else prompt.press(answer)


@pytest.mark.parametrize("answer, opened", [
    ("Don't save", True),
    ("Cancel", False),
    ("dismiss", False),
])
def test_opening_over_unsaved_work_asks_first(tmp_path, video, answer, opened):
    editor = _dirty_editor(video, tmp_path)
    a = tmp_path / "A.vidkid"
    b = _write_project(tmp_path / "B.vidkid", video)

    assert editor.open_project(b) is False, "it waits for the answer"
    prompt = editor.app.banner.current
    assert prompt.message == "Save the current project before opening something else?"
    assert editor.current_project_path == str(a)

    _answer(prompt, answer)
    expected = b if opened else a
    assert Path(editor.current_project_path) == expected.resolve()


def test_save_then_open_needs_the_save_to_work(tmp_path, video, monkeypatch):
    editor = _dirty_editor(video, tmp_path)
    b = _write_project(tmp_path / "B.vidkid", video)

    def disk_full(*args):
        raise OSError("disk full")

    monkeypatch.setattr(project_files, "save_document", disk_full)
    editor.open_project(b)
    editor.app.banner.current.press("Save")
    assert Path(editor.current_project_path) == (tmp_path / "A.vidkid").resolve()
    assert editor.notes[-1][0] == "error"


def test_only_the_newest_open_goes_ahead(tmp_path, video):
    editor = _dirty_editor(video, tmp_path)
    b = _write_project(tmp_path / "B.vidkid", video)
    c = _write_project(tmp_path / "C.vidkid", video)
    editor.open_project(b)
    editor.open_project(c)
    assert editor.app.banner.pending == [], "the question is replaced, not stacked"
    editor.app.banner.current.press("Don't save")
    assert Path(editor.current_project_path) == c.resolve()


@pytest.mark.parametrize("answer, closes, autosave_kept", [
    ("Save", True, False),
    ("Don't save", True, False),
    ("Cancel", False, True),
    ("dismiss", False, True),
])
def test_closing_with_unsaved_work_asks_in_the_banner(
        tmp_path, video, answer, closes, autosave_kept):
    editor = _dirty_editor(video, tmp_path)
    outcome = []
    editor.request_close(lambda: outcome.append("closed"),
                         cancel=lambda: outcome.append("stayed"))
    prompt = editor.app.banner.current
    assert prompt.message == "Save your project before closing?"
    assert outcome == []
    # Written before asking, so an unanswered question loses nothing.
    assert project_files.autosave_path().is_file()

    _answer(prompt, answer)
    assert outcome == (["closed"] if closes else ["stayed"])
    assert project_files.autosave_path().is_file() is autosave_kept


def test_a_failed_save_cancels_the_close(tmp_path, video, monkeypatch):
    editor = _dirty_editor(video, tmp_path)
    editor.current_project_path = None          # Save has to ask where
    monkeypatch.setattr(trim_tab_module.filedialog, "asksaveasfilename", lambda **kw: "")
    outcome = []
    editor.request_close(lambda: outcome.append("closed"),
                         cancel=lambda: outcome.append("stayed"))
    editor.app.banner.current.press("Save")
    assert outcome == ["stayed"]
    assert project_files.autosave_path().is_file()


def test_the_question_names_a_restart(tmp_path, video):
    editor = _dirty_editor(video, tmp_path)
    editor.request_close(lambda: None, verb="restart")
    assert editor.app.banner.current.message == "Save your project before restarting?"


def test_closing_a_clean_project_drops_its_autosave(video):
    _write_project(project_files.autosave_path(), video)
    editor = _editor(str(video))
    closed = []
    editor.request_close(lambda: closed.append(True))
    assert closed == [True]
    assert editor.app.banner.current is None
    assert not project_files.autosave_path().exists()


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
