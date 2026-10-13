# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""One window, no popups: the panels that replaced small windows.

- Export progress, now under the Export button (running, done, failed,
  stopped), and the export worker reporting to it.
- The colour palette that replaced the operating system's colour dialog.
- "Captions from speech" in the Text tab, wired to the transcriber.
- "Record your screen" in Import, wired to the recorder.

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
from videokidnapper.ui.studio.color_palette import (  # noqa: E402
    PRESETS, ColorPalette, normalize_hex, preset_name,
)
from videokidnapper.ui.trim_tab import TrimTab  # noqa: E402
from videokidnapper.utils import settings  # noqa: E402
from videokidnapper.utils.srt_parser import srt_to_text_layers  # noqa: E402


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


# ---------------------------------------------------------------------------
# Colour palette
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("value, expected", [
    ("#ff8800", "#FF8800"),
    ("FF8800", "#FF8800"),
    ("  #12ab34  ", "#12AB34"),
    ("#abc", "#AABBCC"),
    ("abc", "#AABBCC"),
    ("white", "#FFFFFF"),
    ("Black", "#000000"),
    ("Red", "#FF0000"),
    ("pink", "#FF69B4"),
])
def test_normalize_hex_accepts_codes_and_preset_names(value, expected):
    assert normalize_hex(value) == expected


@pytest.mark.parametrize("value", [
    "", "#", "#12345", "#1234567", "#GGGGGG", "reddish", "Custom #FFFFFF",
    None, 0xFFFFFF, ["#FFFFFF"],
])
def test_normalize_hex_rejects_everything_else(value):
    assert normalize_hex(value) is None


def test_presets_are_hex_and_named():
    assert [name for name, _hex in PRESETS][:2] == ["White", "Black"]
    assert all(normalize_hex(value) == value for _name, value in PRESETS)
    assert preset_name("#ff0000") == "Red"
    assert preset_name("white") == "White"
    assert preset_name("#123456") is None
    assert preset_name("nonsense") is None


@pytest.fixture
def palette(root):
    picked = []
    widget = ColorPalette(root, command=picked.append)
    widget.pack()
    widget.picked = picked
    yield widget
    widget.destroy()


def test_swatch_click_reports_its_hex(palette):
    palette.swatches["#FF0000"].invoke()
    assert palette.picked == ["#FF0000"]
    assert palette.get() == "#FF0000"
    assert palette.var.get() == "#FF0000"
    assert palette.name_label.cget("text") == "Red"
    palette.swatches["#FF0000"].invoke()  # same colour again: no change event
    assert palette.picked == ["#FF0000"]


def test_typed_hex_is_normalised_and_reported(palette):
    palette.var.set("12ab34")
    palette._entered()
    assert palette.picked == ["#12AB34"]
    assert palette.var.get() == "#12AB34"
    assert palette.name_label.cget("text") == "Custom"


def test_bad_hex_puts_the_colour_back(palette):
    palette.set("#00FFFF")
    palette.var.set("not a colour")
    palette._entered()
    assert palette.picked == []
    assert palette.get() == "#00FFFF"
    assert palette.var.get() == "#00FFFF"


def test_set_shows_without_reporting(palette):
    palette.set("black")
    assert palette.get() == "#000000"
    assert palette.var.get() == "#000000"
    assert palette.picked == []
    palette.set("rubbish")  # ignored
    assert palette.get() == "#000000"


def test_caption_edits_leave_a_half_typed_code_alone(palette):
    """The Inspector re-shows the colour on every caption edit."""
    palette.set("#FF0000")
    palette.var.set("#12")
    palette.set("#ff0000")  # same colour: nothing to redraw
    assert palette.var.get() == "#12"
    palette.set("#00FF00")  # a different colour does replace it
    assert palette.var.get() == "#00FF00"


@pytest.fixture
def text_layer(root):
    from videokidnapper.ui.text_layers import TextLayerWidget

    widget = TextLayerWidget(root, layer_index=0, video_duration=10.0)
    yield widget
    widget.destroy()


def test_preset_colours_are_stored_as_before(text_layer):
    """Picking White from the palette stores what picking it by name did."""
    assert text_layer.set_color("#FFFFFF")
    assert text_layer.color_var.get() == "White"
    assert text_layer.get_layer_data()["fontcolor"] == "white"
    assert text_layer.set_color("#ff0000")
    assert text_layer.color_var.get() == "Red"
    assert text_layer.get_layer_data()["fontcolor"] == "#FF0000"


def test_custom_colours_are_stored_as_hex(text_layer):
    assert text_layer.set_color("#12ab34")
    assert text_layer.color_var.get() == "Custom #12AB34"
    assert text_layer.get_layer_data()["fontcolor"] == "#12AB34"
    assert text_layer.color_value() == "#12AB34"


def test_not_a_colour_changes_nothing(text_layer):
    text_layer.set_color("#00FF00")
    assert not text_layer.set_color("greenish")
    assert text_layer.get_layer_data()["fontcolor"] == "#00FF00"


def test_custom_colour_round_trips_through_layer_data(root, text_layer):
    from videokidnapper.ui.text_layers import TextLayerWidget

    text_layer.set_color("#ABCDEF")
    copy = TextLayerWidget(root, layer_index=1, video_duration=10.0)
    try:
        copy.load_from_dict(text_layer.get_layer_data())
        assert copy.color_value() == "#ABCDEF"
    finally:
        copy.destroy()


def test_same_colour_does_not_fire_a_change(text_layer):
    fired = []
    text_layer.set_color("#FF8800")
    text_layer.color_var.trace_add("write", lambda *_a: fired.append(1))
    text_layer.set_color("#ff8800")
    assert fired == []


# ---------------------------------------------------------------------------
# Captions from speech
# ---------------------------------------------------------------------------

def _captions_editor(root):
    page = SimpleNamespace(speech=None, opened=0)
    page.show_speech = lambda: setattr(page, "opened", page.opened + 1)
    editor = SimpleNamespace(
        video_path="clip.mp4", notes=[], imported=[], selected=[],
        timeline=SimpleNamespace(get_values=lambda: (2.0, 5.0)),
        captions_btn=SimpleNamespace(configure=lambda **_kw: None),
        inspector=SimpleNamespace(pages={"text": page}),
        after=root.after, page=page,
    )
    editor.text_layers = SimpleNamespace(import_srt_layers=editor.imported.extend)
    editor.select_layer = lambda kind, index: editor.selected.append((kind, index))
    editor._notify = lambda message, level="info": editor.notes.append((level, message))
    return _bind(editor, "generate_captions", "stop_captions", "captions_in_progress",
                 "_speech_box", "_run_whisper_in_background", "_on_captions_progress",
                 "_on_captions_done", "_on_captions_stopped", "_on_captions_failed")


def _speech_box(root, editor):
    from videokidnapper.ui.studio.inspector import SpeechCaptions

    box = SpeechCaptions(root, editor)
    editor.page.speech = box
    return box


@pytest.fixture
def whisper(monkeypatch):
    from videokidnapper.core import whisper_captions

    monkeypatch.setattr(whisper_captions, "is_available", lambda: True)
    return whisper_captions


def test_chosen_model_reaches_the_transcriber(root, whisper, monkeypatch):
    calls = []
    entries = [{"start": 2.5, "end": 3.5, "text": "hello there"}]

    def fake_transcribe(video, model_size="base", start=None, end=None,
                        progress_callback=None, cancel_event=None, **_kw):
        calls.append(dict(video=video, model_size=model_size, start=start, end=end))
        progress_callback(0.5)
        return entries

    monkeypatch.setattr(whisper, "transcribe", fake_transcribe)
    editor = _captions_editor(root)
    box = _speech_box(root, editor)
    try:
        box.model_var.set("small")
        box.go_btn.invoke()
        assert box.running
        assert box.go_btn.cget("text") == "Stop"
        _run_until(root, lambda: not box.running)

        assert calls == [dict(video="clip.mp4", model_size="small", start=2.0, end=5.0)]
        assert editor.imported == srt_to_text_layers(entries)
        assert editor.selected == [("text", 0)]
        assert box.status.cget("text") == "Added 1 caption."
        assert box.go_btn.cget("text") == "Generate captions"
        assert editor.page.opened == 1, "the box stays open for the outcome"
        # Remembered for next time.
        assert settings.get("whisper_model") == "small"
    finally:
        box.destroy()


def test_saved_model_is_preselected_and_bad_values_fall_back(root):
    from videokidnapper.ui.studio.inspector import SpeechCaptions

    editor = _captions_editor(root)
    settings.set("whisper_model", "tiny")
    box = SpeechCaptions(root, editor)
    assert box.model_var.get() == "tiny"
    box.destroy()
    settings.set("whisper_model", "enormous")
    box = SpeechCaptions(root, editor)
    assert box.model_var.get() == "base"
    box.destroy()


def test_missing_faster_whisper_is_explained_inline(root, monkeypatch):
    from videokidnapper.core import whisper_captions

    monkeypatch.setattr(whisper_captions, "is_available", lambda: False)
    monkeypatch.setattr(whisper_captions, "transcribe",
                        lambda *a, **k: pytest.fail("must not transcribe"))
    editor = _captions_editor(root)
    box = _speech_box(root, editor)
    try:
        box.go_btn.invoke()
        assert not box.running
        assert "pip install faster-whisper" in box.status.cget("text")
    finally:
        box.destroy()


def test_stop_discards_the_partial_transcript(root, whisper, monkeypatch):
    def slow_transcribe(*_a, cancel_event=None, **_kw):
        cancel_event.wait(5)
        return [{"start": 2.0, "end": 2.5, "text": "half a sentence"}]

    monkeypatch.setattr(whisper, "transcribe", slow_transcribe)
    editor = _captions_editor(root)
    box = _speech_box(root, editor)
    try:
        box.go_btn.invoke()
        box.go_btn.invoke()  # Stop
        assert box.go_btn.cget("text") == "Stopping…"
        _run_until(root, lambda: not box.running)
        assert editor.imported == []
        assert box.status.cget("text") == "Stopped. No captions were added."
    finally:
        box.destroy()


def test_a_failed_transcription_shows_the_error(root, whisper, monkeypatch):
    def broken(*_a, **_kw):
        raise RuntimeError("ffmpeg failed to extract audio")

    monkeypatch.setattr(whisper, "transcribe", broken)
    editor = _captions_editor(root)
    box = _speech_box(root, editor)
    try:
        box.go_btn.invoke()
        _run_until(root, lambda: not box.running)
        assert "ffmpeg failed to extract audio" in box.status.cget("text")
        assert editor.imported == []
    finally:
        box.destroy()


# ---------------------------------------------------------------------------
# Record your screen
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text, expected", [
    ("10", 10), (" 45 ", 45), ("12.7", 12), ("0", 1), ("-5", 1),
    ("500", 120), ("abc", 10), ("", 10), (None, 10),
])
def test_record_length_is_kept_within_limits(text, expected):
    from videokidnapper.ui.studio.import_workspace import record_seconds

    assert record_seconds(text) == expected


def _record_editor(root, tmp_path):
    window = SimpleNamespace(events=[])
    window.iconify = lambda: window.events.append("iconify")
    window.deiconify = lambda: window.events.append("deiconify")
    editor = SimpleNamespace(
        notes=[], loaded=[], window=window, after=root.after,
        export_options=SimpleNamespace(get_output_folder=lambda: str(tmp_path)),
        quality_var=_Var("Medium"),
    )
    editor.winfo_toplevel = lambda: window
    editor._notify = lambda message, level="info": editor.notes.append((level, message))
    editor._load_path = lambda path: editor.loaded.append(path) or True
    return _bind(editor, "start_screen_recording", "stop_screen_recording",
                 "screen_recording_in_progress", "_on_record_elapsed",
                 "_on_record_encoding", "_on_record_done", "_on_record_stopped",
                 "_on_record_failed")


@pytest.fixture
def no_wait(monkeypatch):
    # The worker waits for the window to minimize; nothing minimizes here.
    monkeypatch.setattr(trim_tab_module, "time", SimpleNamespace(sleep=lambda _s: None))


def _record_panel(root, editor):
    from videokidnapper.ui.studio.import_workspace import RecordPanel

    panel = RecordPanel(root, editor)
    editor.record_panel = panel
    return panel


def test_recording_runs_from_the_import_page(root, tmp_path, monkeypatch, no_wait):
    recorded, encoded = [], []

    def fake_record(seconds, fps=15, cancel_event=None, progress_callback=None, **_kw):
        recorded.append((seconds, fps, cancel_event))
        progress_callback(0.0)
        progress_callback(1.4)
        return tmp_path, fps, 30

    def fake_encode(frame_dir, fps, preset, output):
        encoded.append(output)
        return output

    monkeypatch.setattr(trim_tab_module, "record_screen", fake_record)
    monkeypatch.setattr(trim_tab_module, "frames_to_video", fake_encode)
    editor = _record_editor(root, tmp_path)
    panel = _record_panel(root, editor)
    try:
        panel.seconds_var.set("7")
        panel.start_btn.invoke()
        assert panel.running
        assert panel.start_btn.cget("text") == "Stop recording"
        _run_until(root, lambda: not panel.running)

        assert [r[:2] for r in recorded] == [(7, 15)]
        assert recorded[0][2] is editor._record_cancel
        assert editor.window.events == ["iconify", "deiconify"]
        assert editor.loaded == encoded and len(encoded) == 1
        assert panel.status.cget("text").startswith("Recorded ")
        assert panel.start_btn.cget("text") == "Start recording"
        assert settings.get("record_seconds") == 7
    finally:
        panel.destroy()


def test_stop_before_any_frames_records_nothing(root, tmp_path, monkeypatch, no_wait):
    def waiting_record(seconds, fps=15, cancel_event=None, **_kw):
        cancel_event.wait(5)
        return tmp_path, fps, 0

    monkeypatch.setattr(trim_tab_module, "record_screen", waiting_record)
    monkeypatch.setattr(trim_tab_module, "frames_to_video",
                        lambda *a, **k: pytest.fail("nothing to encode"))
    editor = _record_editor(root, tmp_path)
    panel = _record_panel(root, editor)
    try:
        panel.start_btn.invoke()
        panel.start_btn.invoke()  # Stop
        _run_until(root, lambda: not panel.running)
        assert editor.loaded == []
        assert editor.window.events == ["iconify", "deiconify"]
        assert panel.status.cget("text") == "Stopped before anything was recorded."
    finally:
        panel.destroy()


def test_a_failed_recording_brings_the_window_back(root, tmp_path, monkeypatch, no_wait):
    def broken(*_a, **_k):
        raise OSError("no monitor")

    monkeypatch.setattr(trim_tab_module, "record_screen", broken)
    editor = _record_editor(root, tmp_path)
    panel = _record_panel(root, editor)
    try:
        panel.start_btn.invoke()
        _run_until(root, lambda: not panel.running)
        assert editor.window.events == ["iconify", "deiconify"]
        assert panel.status.cget("text") == "Recording failed: no monitor"
    finally:
        panel.destroy()
