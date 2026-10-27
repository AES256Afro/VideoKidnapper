# SPDX-FileCopyrightText: 2026 AES256Afro <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Closing, restarting and updating ask in the banner, never in a popup.

``App.close_then`` is the one way out of the app. It used to be a
synchronous yes/no with message boxes; now it asks in the banner and
carries on from the answer. These tests drive the real App and TrimTab
methods against stand-ins, so no window is created; answering a prompt
is what a click on its button does.
"""

import subprocess
from types import SimpleNamespace

import pytest

from tests.test_project_safety import _editor, _write_project
from videokidnapper import app as app_module
from videokidnapper.ui import theme as T
from videokidnapper.ui import trim_tab as trim_tab_module
from videokidnapper.ui.studio.banner import PromptQueue
from videokidnapper.utils import project_files

EXPORT_QUESTION = "An export is still running. Stop it and close VideoKidnapper?"
SAVE_QUESTION = "Save your project before closing?"


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(project_files.settings, "_SETTINGS_PATH", tmp_path / "settings.json")
    monkeypatch.setattr(trim_tab_module.settings, "add_recent_project", lambda path: None)


@pytest.fixture
def video(tmp_path):
    path = tmp_path / "clip.mp4"
    path.write_bytes(b"video")
    return path


class _Export:
    """An export page: the editor's own export or the Batch page."""

    def __init__(self, events, name, running=True):
        self.events, self.name, self.running = events, name, running

    def export_in_progress(self):
        return self.running

    def stop_export(self):
        self.events.append(f"stop {self.name}")
        self.running = False


def _app(editor=None, batch=None):
    """Enough of App for the close flow, sharing the editor's banner."""
    events = []
    app = SimpleNamespace(
        banner=PromptQueue(), trim_tab=editor, _built_tabs={}, events=events,
        status_bar=SimpleNamespace(show=lambda message, level="info":
                                   events.append(f"status: {message}")),
        destroy=lambda: events.append("destroy"),
    )
    if batch is not None:
        app._built_tabs[app_module.TAB_BATCH] = batch
    for name in ("close_then", "_ask_to_stop_exports", "_running_exports",
                 "_request_close", "_restart_app", "_relaunch", "_pick_theme"):
        setattr(app, name, getattr(app_module.App, name).__get__(app))
    if editor is not None:
        editor.app = app
    return app


def _dirty(video, tmp_path):
    editor = _editor(str(video))
    editor.current_project_path = str(_write_project(tmp_path / "A.vidkid", video))
    editor._project_dirty = True
    return editor


def _running_editor(editor, events):
    """Give the stand-in editor an export of its own that is running."""
    export = _Export(events, "edit")
    editor.export_in_progress = export.export_in_progress
    editor.stop_export = export.stop_export
    return export


# -- nothing to ask -----------------------------------------------------------------

def test_nothing_running_and_nothing_unsaved_closes_at_once(video):
    app = _app(_editor(str(video)))
    app._request_close()
    assert app.events == ["destroy"]
    assert app.banner.current is None


def test_the_setup_landing_has_no_editor_and_still_closes():
    app = _app()
    app._request_close()
    assert app.events == ["destroy"]


def test_recovery_prompt_up_closes_and_keeps_the_autosave(video):
    _write_project(project_files.autosave_path(), video)
    editor = _editor(None)
    app = _app(editor)
    editor.offer_recovery(project_files.autosave_path())
    app._request_close()
    assert app.events == ["destroy"]
    assert project_files.autosave_path().is_file()


# -- unsaved work ------------------------------------------------------------------

@pytest.mark.parametrize("answer, ends", [
    ("Save", True), ("Don't save", True), ("Cancel", False), ("dismiss", False),
])
def test_unsaved_work_is_asked_about_and_the_close_waits(tmp_path, video, answer, ends):
    app = _app(_dirty(video, tmp_path))
    cancelled = []
    app.close_then(app.destroy, on_cancel=lambda: cancelled.append(True))
    assert app.events == [], "close_then returns without closing"
    prompt = app.banner.current
    assert prompt.message == SAVE_QUESTION
    assert [b.label for b in prompt.buttons] == ["Save", "Don't save", "Cancel"]

    prompt.dismiss() if answer == "dismiss" else prompt.press(answer)
    assert app.events == (["destroy"] if ends else [])
    assert cancelled == ([] if ends else [True])


def test_a_save_that_fails_keeps_the_app_open(tmp_path, video, monkeypatch):
    editor = _dirty(video, tmp_path)
    editor.current_project_path = None
    monkeypatch.setattr(trim_tab_module.filedialog, "asksaveasfilename", lambda **kw: "")
    app = _app(editor)
    app._request_close()
    app.banner.current.press("Save")
    assert app.events == []
    assert project_files.autosave_path().is_file()


def test_a_second_close_replaces_the_first_question(tmp_path, video):
    app = _app(_dirty(video, tmp_path))
    app._request_close()
    app._request_close()
    assert app.banner.pending == []
    app.banner.current.press("Don't save")
    assert app.events == ["destroy"], "closed once, not twice"


def test_the_close_question_jumps_ahead_of_a_waiting_prompt(tmp_path, video):
    app = _app(_dirty(video, tmp_path))
    theme = app.banner.ask("Theme set to Retro. Restart to apply it.")
    app._request_close()
    assert app.banner.current.message == SAVE_QUESTION
    app.banner.current.press("Cancel")
    assert app.banner.current is theme


# -- running exports -------------------------------------------------------------------

def test_keep_exporting_leaves_everything_running(video):
    app = _app(_editor(str(video)))
    batch = _Export(app.events, "batch")
    app._built_tabs[app_module.TAB_BATCH] = batch
    app._request_close()
    prompt = app.banner.current
    assert prompt.message == EXPORT_QUESTION
    assert prompt.tone == "warn"
    prompt.press("Keep exporting")
    assert app.events == []
    assert batch.running


def test_stop_and_close_stops_the_export_then_closes(video):
    app = _app(_editor(str(video)))
    app._built_tabs[app_module.TAB_BATCH] = _Export(app.events, "batch")
    app._request_close()
    app.banner.current.press("Stop and close")
    assert app.events == ["stop batch", "destroy"]


def test_the_export_is_stopped_only_after_the_save_question(tmp_path, video):
    editor = _dirty(video, tmp_path)
    app = _app(editor)
    export = _running_editor(editor, app.events)

    app._request_close()
    app.banner.current.press("Stop and close")
    assert app.banner.current.message == SAVE_QUESTION
    assert export.running, "not stopped while the save question is open"

    app.banner.current.press("Cancel")
    assert export.running and app.events == []

    app._request_close()
    app.banner.current.press("Stop and close")
    app.banner.current.press("Don't save")
    assert app.events == ["stop edit", "destroy"]


def test_a_failed_save_leaves_the_export_running(tmp_path, video, monkeypatch):
    editor = _dirty(video, tmp_path)
    editor.current_project_path = None
    monkeypatch.setattr(trim_tab_module.filedialog, "asksaveasfilename", lambda **kw: "")
    app = _app(editor)
    export = _running_editor(editor, app.events)
    app._request_close()
    app.banner.current.press("Stop and close")
    app.banner.current.press("Save")
    assert export.running
    assert app.events == []


def test_an_export_started_during_the_question_is_asked_about(tmp_path, video):
    app = _app(_dirty(video, tmp_path))
    app._request_close()
    batch = _Export(app.events, "batch")
    app._built_tabs[app_module.TAB_BATCH] = batch   # started meanwhile
    app.banner.current.press("Don't save")
    assert app.banner.current.message == EXPORT_QUESTION
    assert batch.running and app.events == []
    app.banner.current.press("Stop and close")
    assert app.events == ["stop batch", "destroy"]


# -- restart and the theme ------------------------------------------------------------------

@pytest.fixture
def launches(monkeypatch):
    started = []
    monkeypatch.setattr(subprocess, "Popen", lambda args, **kw: started.append(args))
    return started


def test_restart_asks_what_closing_asks_then_relaunches(tmp_path, video, launches):
    app = _app(_dirty(video, tmp_path))
    app._built_tabs[app_module.TAB_BATCH] = _Export(app.events, "batch")
    app._restart_app()
    prompt = app.banner.current
    assert prompt.message == "An export is still running. Stop it and restart VideoKidnapper?"
    prompt.press("Stop and restart")
    assert app.banner.current.message == "Save your project before restarting?"
    assert launches == []
    app.banner.current.press("Don't save")
    assert len(launches) == 1
    assert app.events == ["stop batch", "destroy"]


def test_a_cancelled_restart_does_not_relaunch(tmp_path, video, launches):
    app = _app(_dirty(video, tmp_path))
    app._restart_app()
    app.banner.current.press("Cancel")
    assert launches == [] and app.events == []


def test_theme_change_offers_the_restart_in_the_banner(video, monkeypatch, launches):
    monkeypatch.setattr(T, "current_theme", lambda: "light")
    picked = []
    monkeypatch.setattr(T, "set_theme", picked.append)
    app = _app(_editor(str(video)))

    app._pick_theme("retro")
    app._pick_theme("fallout")
    assert picked == ["retro", "fallout"]
    assert app.banner.pending == [], "a second pick rewords the prompt"
    prompt = app.banner.current
    assert prompt.message == "Theme set to Fallout. Restart to apply it."
    assert [b.label for b in prompt.buttons] == ["Restart now", "Later"]

    prompt.press("Later")
    assert app.events == ["status: Theme set to Fallout — restart VideoKidnapper to apply."]

    app._pick_theme("retro")
    app.banner.current.press("Restart now")
    assert len(launches) == 1
    assert app.events[-1] == "destroy"


def test_picking_the_current_theme_asks_nothing(video, monkeypatch):
    monkeypatch.setattr(T, "current_theme", lambda: "light")
    app = _app(_editor(str(video)))
    app._pick_theme("light")
    assert app.banner.current is None


def test_no_message_boxes_left_in_the_close_paths():
    """The popups are gone for good: no message box in the app or editor."""
    import inspect

    for module in (app_module, trim_tab_module):
        assert "messagebox" not in inspect.getsource(module)
