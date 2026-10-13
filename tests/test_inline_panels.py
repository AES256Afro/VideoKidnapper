# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""One window, no popups: the panels that replaced small windows.

- Export progress, now under the Export button (running, done, failed,
  stopped), and the export worker reporting to it.

The editor methods run against small stand-ins with the slow parts
stubbed, so nothing is encoded, transcribed or recorded. The one Tk root
stays withdrawn, so no window ever shows.
"""

import time
from types import SimpleNamespace

import pytest

ctk = pytest.importorskip("customtkinter", reason="needs customtkinter")

from videokidnapper.ui import trim_tab as trim_tab_module  # noqa: E402
from videokidnapper.ui.studio import export_progress as ep  # noqa: E402
from videokidnapper.ui.trim_tab import TrimTab  # noqa: E402
from videokidnapper.utils import settings  # noqa: E402


@pytest.fixture(scope="module")
def root():
    """One withdrawn root for the module (Tk dislikes being rebuilt)."""
    try:
        instance = ctk.CTk()
    except Exception as exc:  # pragma: no cover - headless CI
        pytest.skip(f"no usable display: {type(exc).__name__}: {exc}")
    instance.withdraw()
    yield instance
    try:
        instance.destroy()
    except Exception:
        pass


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "_SETTINGS_PATH", tmp_path / "settings.json")


def _run_until(root, done, timeout=10.0):
    """Run Tk's main loop until ``done()``.

    The workers hand their Tk calls (``after``) to the main thread, and
    tkinter only accepts those while the main loop is running; a bare
    ``update()`` loop would make them fail.
    """
    deadline = time.monotonic() + timeout

    def check():
        if done() or time.monotonic() > deadline:
            root.quit()
        else:
            root.after(20, check)

    root.after(20, check)
    root.mainloop()
    assert done(), "the worker did not finish in time"


def _packed(widget):
    return widget.winfo_manager() == "pack"


def _bind(editor, *names):
    for name in names:
        setattr(editor, name, getattr(TrimTab, name).__get__(editor))
    return editor


# ---------------------------------------------------------------------------
# Export progress
# ---------------------------------------------------------------------------

@pytest.fixture
def panel(root):
    started = []
    widget = ep.ExportProgress(root, on_export=lambda: started.append(1))
    widget.pack(fill="x")
    widget.set_ready("Export 1 file", True)
    widget.started = started
    yield widget
    widget.destroy()


def test_idle_panel_is_just_the_export_button(panel):
    assert panel.state == ep.IDLE
    assert not _packed(panel.area)
    assert panel.button.cget("text") == "Export 1 file"
    panel.button.invoke()
    assert panel.started == [1]


def test_running_then_done_shows_the_file_and_its_actions(panel, tmp_path):
    job = panel.begin("Exporting 2 clips…")
    assert panel.state == ep.RUNNING
    assert _packed(panel.area) and _packed(panel.bar)
    assert panel.button.cget("text") == "Stop export"
    assert panel.status_label.cget("text") == "Exporting 2 clips…"

    job.update_progress(0.5, "Clip 2/2 — encoding MP4...")
    assert panel.percent_label.cget("text") == "50%"
    assert panel.status_label.cget("text") == "Clip 2/2 — encoding MP4..."
    assert abs(panel.bar.get() - 0.5) < 0.01

    out = tmp_path / "clip.mp4"
    out.write_bytes(b"video")
    job.export_complete(str(out))
    assert panel.state == ep.DONE
    assert panel.output_path == str(out)
    assert "clip.mp4" in panel.status_label.cget("text")
    assert _packed(panel.result_row) and not _packed(panel.bar)
    assert panel.share_panel is not None and _packed(panel.share_panel)
    # Back to Export, ready for the next run.
    assert panel.button.cget("text") == "Export 1 file"
    assert panel.button.cget("state") == "normal"

    panel.dismiss()
    assert panel.state == ep.IDLE
    assert not _packed(panel.area)
    assert panel.share_panel is None


def test_failure_says_what_went_wrong(panel):
    job = panel.begin("Exporting 1 clip…")
    job.export_failed("Clip 1 failed — aborting")
    assert panel.state == ep.FAILED
    assert panel.status_label.cget("text") == "Clip 1 failed — aborting"
    assert not _packed(panel.result_row)
    assert _packed(panel.dismiss_btn)
    assert panel.button.cget("text") == "Export 1 file"


def test_export_button_turns_into_stop_while_running(panel):
    job = panel.begin("Exporting 1 clip…")
    panel.button.invoke()  # pressed again mid-run: Stop, not a second export
    assert panel.started == []
    assert job.cancel_event.is_set()
    assert panel.state == ep.STOPPING
    assert panel.button.cget("state") == "disabled"
    panel.button.invoke()  # disabled while stopping: nothing happens
    assert panel.started == []

    # A clip "fails" because ffmpeg was killed: that's the stop, not an error.
    job.export_failed("Clip 1 failed — aborting")
    assert panel.state == ep.CANCELLED
    assert panel.status_label.cget("text") == "Export stopped."
    assert panel.button.cget("text") == "Export 1 file"


def test_a_finished_run_cannot_be_stopped_and_a_running_one_not_dismissed(panel):
    job = panel.begin("Exporting 1 clip…")
    panel.dismiss()
    assert panel.state == ep.RUNNING
    job.export_failed("boom")
    panel.stop()
    assert panel.state == ep.FAILED
    assert not job.cancel_event.is_set()


def test_reports_from_an_earlier_run_are_ignored(panel, tmp_path):
    old = panel.begin("Exporting 1 clip…")
    old.export_failed("first run failed")
    new = panel.begin("Exporting 1 clip…")
    assert not old.winfo_exists() and new.winfo_exists()

    old.update_progress(0.9, "stale")
    old.export_complete(str(tmp_path / "stale.mp4"))
    assert panel.state == ep.RUNNING
    assert panel.status_label.cget("text") == "Exporting 1 clip…"
    assert panel.percent_label.cget("text") == "0%"


def test_ready_text_waits_until_the_run_ends(panel):
    job = panel.begin("Exporting 1 clip…")
    panel.set_ready("Export 3 files", True)
    assert panel.button.cget("text") == "Stop export"
    job.export_failed("nope")
    assert panel.button.cget("text") == "Export 3 files"
    panel.set_ready("Export", False)
    assert panel.button.cget("state") == "disabled"


class _Var:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value


def _export_editor(root, panel, tmp_path, ranges):
    shown = []
    editor = SimpleNamespace(
        video_path=str(tmp_path / "source.mp4"), source_title="source",
        export_progress=panel, app=SimpleNamespace(),
        quality_var=_Var("Medium"), format_var=_Var("MP4"),
        export_options=SimpleNamespace(
            get_options=lambda: {}, get_output_folder=lambda: str(tmp_path / "out")),
        text_layers=SimpleNamespace(get_all_layers=lambda: []),
        image_layers=SimpleNamespace(get_all_layers=lambda: []),
        notes=[], shown=shown, history=[],
    )
    editor._gather_ranges = lambda: list(ranges)
    editor._notify = lambda message, level="info": editor.notes.append((level, message))
    editor._show_workspace = shown.append
    editor._record_history = lambda path, *_a: editor.history.append(path)
    return _bind(editor, "_export", "_show_export_progress", "export_in_progress")


def test_export_worker_reports_to_the_inline_panel(root, panel, tmp_path, monkeypatch):
    calls = []

    def fake_trim(src, start, end, preset, output_path, progress_callback=None,
                  cancel_event=None, **_kwargs):
        calls.append((start, end, cancel_event))
        progress_callback(0.5)
        progress_callback(1.0)
        with open(output_path, "wb") as fh:
            fh.write(b"mp4")
        return output_path

    monkeypatch.setattr(trim_tab_module, "trim_to_video", fake_trim)
    editor = _export_editor(root, panel, tmp_path, [(0.0, 1.0), (2.0, 3.0)])

    editor._export()
    assert editor.shown == ["export"], "progress lives in the Export workspace"
    assert panel.state == ep.RUNNING
    _run_until(root, lambda: panel.state == ep.DONE)

    assert [c[:2] for c in calls] == [(0.0, 1.0), (2.0, 3.0)]
    assert all(c[2] is editor._export_cancel for c in calls)
    assert panel.output_path and panel.output_path.endswith(".mp4")
    assert editor.history == [panel.output_path]


def test_export_pressed_while_one_runs_starts_nothing(root, panel, tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(trim_tab_module, "trim_to_video",
                        lambda *a, **k: calls.append(1))
    editor = _export_editor(root, panel, tmp_path, [(0.0, 1.0)])
    panel.begin("Exporting 1 clip…")  # a run is already going
    editor._export()
    assert calls == []
    assert ("warn", "An export is already running. Stop it first.") in editor.notes


def test_stopping_an_export_records_nothing(root, panel, tmp_path, monkeypatch):
    def fake_trim(*_a, cancel_event=None, **_k):
        cancel_event.wait(5)
        return None  # ffmpeg was killed

    monkeypatch.setattr(trim_tab_module, "trim_to_video", fake_trim)
    editor = _export_editor(root, panel, tmp_path, [(0.0, 1.0), (2.0, 3.0)])
    editor._export()
    panel.button.invoke()  # Stop
    _run_until(root, lambda: panel.state == ep.CANCELLED)
    assert editor.history == []
    assert ("warn", "Export stopped") in editor.notes


