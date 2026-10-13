# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Regressions from a bug sweep of captions, batch export and downloads.

Widget state only: the Tk root is withdrawn as soon as it exists and no
window is ever shown. Nothing here touches the network; downloads and
encodes are replaced by stand-ins where a test needs them.
"""

import shutil
import subprocess
import time
import types

import pytest

from tests.test_corrupt_layer_values import HOSTILE_TEXT_LAYERS

ctk = pytest.importorskip("customtkinter")

_HAS_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


@pytest.fixture(scope="module")
def root():
    try:
        r = ctk.CTk()
    except Exception as exc:  # noqa: BLE001 - headless CI
        pytest.skip(f"no usable display: {type(exc).__name__}")
    r.withdraw()
    yield r
    r.destroy()


@pytest.fixture(scope="module")
def clip(tmp_path_factory):
    """6 s test pattern, 320x180, no audio."""
    if not _HAS_FFMPEG:
        pytest.skip("ffmpeg / ffprobe not on PATH")
    path = tmp_path_factory.mktemp("clip") / "clip.mp4"
    subprocess.run([
        "ffmpeg", "-v", "error", "-y",
        "-f", "lavfi", "-i", "testsrc=size=320x180:rate=24:duration=6",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        str(path),
    ], check=True, capture_output=True, timeout=60)
    return path


@pytest.fixture(scope="module")
def editor(root, clip, tmp_path_factory):
    from videokidnapper.utils import settings

    mp = pytest.MonkeyPatch()
    mp.setattr(settings, "_SETTINGS_PATH",
               tmp_path_factory.mktemp("home") / "settings.json")
    from videokidnapper.ui.trim_tab import TrimTab

    ed = TrimTab(root, types.SimpleNamespace(show_workspace=lambda _key: None))
    ed.pack(fill="both", expand=True)
    assert ed._load_path(str(clip))
    yield ed
    ed._project_dirty = False
    ed.destroy()
    mp.undo()


def _descendants(widget):
    found = []
    for child in widget.winfo_children():
        found.append(child)
        found.extend(_descendants(child))
    return found


def _cues(n, length=6.0):
    lines = []
    for i in range(n):
        start = (i * 0.017) % (length - 0.5)
        lines.append({"start": start, "end": start + 0.4, "text": f"line {i}"})
    return lines


# ---------------------------------------------------------------------------
# Captions are data, not widgets
# ---------------------------------------------------------------------------

def test_captions_build_no_widgets(root):
    """Each caption built a hidden row of ~30 widgets and four menus;
    a few hundred of them exhausted Windows' menus mid-import."""
    from videokidnapper.ui.text_layers import TextLayersPanel
    from videokidnapper.utils.srt_parser import srt_to_text_layers

    panel = TextLayersPanel(root)
    panel.set_duration(6.0)
    before = len(_descendants(panel))
    panel.import_srt_layers(srt_to_text_layers(_cues(5)))
    assert len(panel.layers) == 5
    assert len(_descendants(panel)) == before
    panel.destroy()


def test_import_sends_one_change_notification(root):
    from videokidnapper.ui.text_layers import TextLayersPanel
    from videokidnapper.utils.srt_parser import srt_to_text_layers

    calls = []
    panel = TextLayersPanel(root, on_change=lambda: calls.append(1))
    panel.set_duration(6.0)
    assert panel.import_srt_layers(srt_to_text_layers(_cues(40))) == 40
    assert len(calls) == 1
    panel.destroy()


def test_caption_round_trip(root):
    """What the Inspector, undo and projects rely on still holds."""
    from videokidnapper.ui.text_layers import TextLayersPanel

    panel = TextLayersPanel(root)
    panel.set_duration(10.0)
    data = {
        "text": "two\nlines", "font": "Georgia", "fontsize": 40,
        "fontcolor": "#123456", "position": "120:80", "box": False,
        "bold": True, "italic": True, "borderw": 3, "shadowx": 4, "shadowy": 5,
        "start": 1.5, "end": 4.0,
        "keyframes": [{"t": 2.0, "x": 10.0, "y": 20.0}, {"t": 3.0, "x": 30.0, "y": 40.0}],
    }
    layer = panel._add_layer(preset_data=data)
    out = layer.get_layer_data()
    for key, value in data.items():
        assert out[key] == value, key
    # The slider's old clamping is kept.
    layer.time_slider.set_values(-3, 99)
    assert layer.time_slider.get_values() == (0, 10.0)
    panel.destroy()


def test_large_subtitle_import_is_quick(editor, tmp_path, monkeypatch):
    """A 300-line SRT froze the editor for minutes, then failed with
    "No more menus can be allocated" after about 90 lines."""
    from tkinter import filedialog

    srt = tmp_path / "movie.srt"
    with open(srt, "w", encoding="utf-8") as fh:
        for i, cue in enumerate(_cues(300), 1):
            def tc(t):
                ms = int(round(t * 1000))
                return f"00:00:{ms // 1000:02d},{ms % 1000:03d}"
            fh.write(f"{i}\n{tc(cue['start'])} --> {tc(cue['end'])}\n{cue['text']}\n\n")
    monkeypatch.setattr(filedialog, "askopenfilename", lambda **_k: str(srt))
    toasts = []
    monkeypatch.setattr(editor, "_notify", lambda m, level="info": toasts.append((level, m)))

    editor.update()     # settle whatever loading the clip queued
    started = time.perf_counter()
    editor._import_srt()
    elapsed = time.perf_counter() - started
    try:
        assert len(editor.text_layers.layers) == 300
        assert toasts[-1][0] == "success", toasts
        assert elapsed < 1.0, f"import took {elapsed:.2f}s"
    finally:
        editor.text_layers.clear_layers()
        editor.selected_text_index = None
        editor._sync_timeline_clips()


# ---------------------------------------------------------------------------
# Loaders: undo, duplicate and project open all go through them
# ---------------------------------------------------------------------------

HOSTILE_LOADER_TEXT_LAYERS = HOSTILE_TEXT_LAYERS + [
    {"text": None, "font": ["Arial"], "fontsize": float("inf"),
     "position": 12, "start": None, "end": float("nan")},
    {"text": 5, "fontsize": -3, "borderw": float("inf"), "shadowx": "1.5",
     "position": ["x"], "fontcolor": {"r": 1}},
    {"text": "hi", "start": 0, "end": 9, "keyframes": [{"t": 1, "y": 2}, "junk"]},
    {"text": "hi", "keyframes": "not a list"},
]


@pytest.mark.parametrize("layer", HOSTILE_LOADER_TEXT_LAYERS)
def test_caption_loader_survives_corrupt_values(root, layer):
    """Opening a project with one of these raised ValueError, TypeError
    or KeyError from the caption loader."""
    from videokidnapper.ui.text_layers import TextLayersPanel

    panel = TextLayersPanel(root)
    panel.set_duration(10.0)
    try:
        caption = panel._add_layer(preset_data=layer)
        data = caption.get_layer_data()
        assert data["fontsize"] > 0
        assert 0.0 <= data["start"] <= 10.0 and 0.0 <= data["end"] <= 10.0
        assert isinstance(data["text"], str) and isinstance(data["font"], str)
        assert "keyframes" not in data
    finally:
        panel.destroy()


@pytest.mark.parametrize("layer", [
    {"path": "/nonexistent.png", "scale": "big", "opacity": "x",
     "x": None, "y": "12abc", "start": "soon", "end": None},
    {"path": ["a.png"], "position": ["top_left"], "scale": float("inf"),
     "x": float("inf"), "y": [], "start": float("nan"), "end": {}},
])
def test_image_loader_survives_corrupt_values(root, layer):
    from videokidnapper.ui.image_layers import ImageLayersPanel

    panel = ImageLayersPanel(root)
    panel.set_duration(10.0)
    try:
        overlay = panel._add_layer(preset_data=layer)
        data = overlay.get_layer_data()
        assert data["scale"] == 0.25 and data["opacity"] == 1.0
        assert "x" not in data and "y" not in data
        assert isinstance(data["path"], str)
    finally:
        panel.destroy()


def test_preview_survives_an_unusable_motion_path(root):
    from PIL import Image

    from videokidnapper.ui.video_player import VideoPlayer

    player = VideoPlayer(root)
    try:
        player.set_text_layers_provider(lambda: [{
            "text": "hi", "start": 0, "end": 9, "keyframes": [{"t": "x"}],
        }])
        player._apply_text_overlay(Image.new("RGB", (160, 120)), 1.0)
    finally:
        player.destroy()


def test_project_with_odd_values_opens_normally(editor, clip, tmp_path):
    """Odd numbers in a shared project used to make the caption and
    sticker loaders raise, so the project opened as "damaged" and
    untitled. They now load with sane values, under the project's name."""
    import json

    from videokidnapper.utils import project_files

    doc = project_files.build_document(
        str(clip),
        {"range": [0.0, 6.0], "queued": [],
         "layers": HOSTILE_LOADER_TEXT_LAYERS,
         "images": [{"path": "", "scale": "big", "x": None, "start": "soon"}]},
        {}, project_path=tmp_path / "odd.vidkid")
    path = project_files.save_document(tmp_path / "odd.vidkid", doc)
    json.loads(path.read_text(encoding="utf-8"))   # really written
    toasts = []
    notify = editor._notify
    editor._notify = lambda m, level="info": toasts.append((level, m))
    editor._project_dirty = False      # no "save first?" question
    try:
        assert editor.open_project(str(path))
        assert editor.current_project_path == str(path.resolve()), toasts
        assert len(editor.text_layers.layers) == len(HOSTILE_LOADER_TEXT_LAYERS)
        assert len(editor.image_layers.layers) == 1
        assert toasts[-1][0] == "success", toasts
    finally:
        editor._notify = notify
        editor._project_dirty = False
        editor.text_layers.clear_layers()
        editor.image_layers.clear_layers()
        editor.selected_text_index = editor.selected_image_index = None


# ---------------------------------------------------------------------------
# Batch export
# ---------------------------------------------------------------------------

def _run_until(root, predicate, timeout=20.0):
    """Run the Tk loop (the batch worker posts to it) until ``predicate``."""
    end = time.monotonic() + timeout

    def poll():
        if predicate() or time.monotonic() > end:
            root.quit()
            return
        root.after(20, poll)

    root.after(20, poll)
    root.mainloop()
    assert predicate(), "timed out"


class _FakeEncoder:
    """Stands in for trim_to_video: writes a partial file, waits to be
    released (or cancelled), then finishes or gives up like ffmpeg."""

    def __init__(self):
        import threading

        self.release = threading.Event()
        self.started = []

    def __call__(self, input_path, start, end, preset, output_path,
                 cancel_event=None, **_kw):
        self.started.append(input_path)
        with open(output_path, "wb") as fh:
            fh.write(b"half a video")
        while not self.release.is_set():
            if cancel_event is not None and cancel_event.is_set():
                return None     # ffmpeg killed; output left behind
            time.sleep(0.01)
        with open(output_path, "wb") as fh:
            fh.write(b"a whole video")
        return output_path


@pytest.fixture
def batch_tab(root, tmp_path, monkeypatch):
    from videokidnapper.ui import batch_export_tab as bet
    from videokidnapper.utils import settings

    monkeypatch.setattr(settings, "_SETTINGS_PATH", tmp_path / "settings.json")
    encoder = _FakeEncoder()
    monkeypatch.setattr(bet, "trim_to_video", encoder)
    monkeypatch.setattr(bet, "get_video_info", lambda _p: {"duration": 5.0})
    tab = bet.BatchExportTab(root, types.SimpleNamespace())
    tab.export_options.output_folder_var.set(str(tmp_path / "out"))
    sources = []
    for name in ("first.mp4", "second.mp4"):
        src = tmp_path / "src" / name
        src.parent.mkdir(exist_ok=True)
        src.write_bytes(b"x")
        sources.append(str(src))
    tab._enqueue(sources)
    tab.encoder = encoder
    yield tab
    encoder.release.set()
    if tab._worker is not None:
        tab._worker.join(5)
    tab.destroy()


def test_stop_after_this_file_finishes_it(root, batch_tab):
    """The button said "Stop after this file" but killed the file being
    exported, marked it Stopped and left half of it on disk."""
    from videokidnapper.utils.batch import STATUS_CANCELLED, STATUS_DONE

    first, second = batch_tab.get_jobs()
    batch_tab._start_batch()
    _run_until(root, lambda: batch_tab.encoder.started)
    batch_tab._stop_batch()
    root.after(200, batch_tab.encoder.release.set)
    _run_until(root, lambda: not batch_tab._running())
    root.update()

    assert first.status == STATUS_DONE
    assert open(first.output_path, "rb").read() == b"a whole video"
    assert second.status == STATUS_CANCELLED
    assert batch_tab.encoder.started == [first.input_path]
    assert batch_tab.stop_btn.cget("text") == "Stop after this file"


def test_second_stop_click_stops_now_and_cleans_up(root, batch_tab):
    from pathlib import Path

    from videokidnapper.utils.batch import STATUS_CANCELLED

    first, second = batch_tab.get_jobs()
    batch_tab._start_batch()
    _run_until(root, lambda: batch_tab.encoder.started)
    batch_tab._stop_batch()
    batch_tab._stop_batch()
    _run_until(root, lambda: not batch_tab._running())
    root.update()

    assert first.status == STATUS_CANCELLED and second.status == STATUS_CANCELLED
    assert not Path(first.output_path).exists()


def test_closing_the_app_still_stops_now(root, batch_tab):
    """stop_export (used when the app closes) keeps meaning "stop now"."""
    from videokidnapper.utils.batch import STATUS_CANCELLED

    first, _second = batch_tab.get_jobs()
    batch_tab._start_batch()
    _run_until(root, lambda: batch_tab.encoder.started)
    assert batch_tab.export_in_progress()
    # As on close: called from a Tk callback, inside the event loop.
    stopped = []
    root.after(0, lambda: (batch_tab.stop_export(timeout=5.0), stopped.append(1)))
    _run_until(root, lambda: stopped)
    assert not batch_tab.export_in_progress()
    root.update()
    assert first.status == STATUS_CANCELLED


def test_batch_rows_follow_save_to_and_format(root, batch_tab, tmp_path):
    """Output paths were fixed when files were added: changing "Save to"
    afterwards still exported to the old folder, and switching the format
    just swapped the extension, overwriting a file already there."""
    from pathlib import Path

    first, second = batch_tab.get_jobs()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "first_batch.mp3").write_bytes(b"keep me")

    batch_tab.export_options.output_folder_var.set(str(elsewhere))
    root.update()
    assert Path(first.output_path).parent == elsewhere
    assert Path(second.output_path).parent == elsewhere

    batch_tab.format_var.set("MP3")
    batch_tab._format_changed("MP3")
    assert Path(first.output_path) == elsewhere / "first_batch_1.mp3"
    assert Path(second.output_path) == elsewhere / "second_batch.mp3"
    assert batch_tab._job_rows[0]["out"].cget("text").endswith("first_batch_1.mp3")


def test_batch_run_replans_before_starting(root, batch_tab, tmp_path):
    """A file that appeared since the rows were planned is not overwritten."""
    from pathlib import Path

    first, _second = batch_tab.get_jobs()
    Path(first.output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(first.output_path).write_bytes(b"someone else's file")
    planned = first.output_path

    batch_tab._start_batch()
    _run_until(root, lambda: batch_tab.encoder.started)
    assert first.output_path != planned
    assert open(planned, "rb").read() == b"someone else's file"
    batch_tab.encoder.release.set()
    _run_until(root, lambda: not batch_tab._running())


# ---------------------------------------------------------------------------
# Downloads
# ---------------------------------------------------------------------------

class _SlowDownload:
    """Stands in for download_video: runs until released or cancelled."""

    def __init__(self):
        import threading

        self.release = threading.Event()
        self.urls = []

    def __call__(self, url, progress_callback=None, cancel_event=None, cookies=None):
        self.urls.append(url)
        while not self.release.is_set():
            if cancel_event is not None and cancel_event.is_set():
                return {"path": None, "title": None, "platform": None,
                        "error": "cancelled"}
            time.sleep(0.01)
        return {"path": None, "title": None, "platform": None, "error": "nope"}


@pytest.fixture
def download_bar(root, monkeypatch, tmp_path):
    from videokidnapper import config
    from videokidnapper.ui import source_bar
    from videokidnapper.utils import settings

    monkeypatch.setattr(settings, "_SETTINGS_PATH", tmp_path / "settings.json")
    # destroy() clears partial downloads; keep it out of the real home.
    monkeypatch.setattr(config, "TEMP_DIR", tmp_path / "temp")
    fake = _SlowDownload()
    monkeypatch.setattr(source_bar, "download_video", fake)
    toasts = []
    bar = source_bar.DownloadBar(root, on_video_ready=lambda *a: None,
                                 notify=lambda m, level="info": toasts.append((level, m)))
    bar.fake, bar.toasts = fake, toasts
    yield bar
    fake.release.set()
    _run_until(root, lambda: not bar.busy(), timeout=5)
    bar.destroy()


def test_link_pasted_during_a_download_is_kept(root, download_bar):
    """The link box was disabled during a download, so Tk ignored a
    pasted link while the toast said "Link pasted"."""
    bar = download_bar
    bar.receive_url("https://youtu.be/AAAAAAAAAAA")
    assert bar._download() is True
    bar.receive_url("https://youtu.be/BBBBBBBBBBB")
    assert bar.url_entry.get() == "https://youtu.be/BBBBBBBBBBB"
    # Pressing Download again starts nothing and keeps the link.
    assert bar._download() is False
    _run_until(root, lambda: bar.fake.urls)
    assert bar.fake.urls == ["https://youtu.be/AAAAAAAAAAA"]
    assert bar.url_entry.get() == "https://youtu.be/BBBBBBBBBBB"


def test_get_link_during_a_download_keeps_it(root, download_bar, editor):
    """The Edit page's "Get" re-downloaded the running link and cleared
    the new one from its box."""
    bar = download_bar
    editor.download_bar = bar
    try:
        bar.receive_url("https://youtu.be/AAAAAAAAAAA")
        bar._download()
        editor.media_link_entry.insert(0, "https://youtu.be/BBBBBBBBBBB")
        editor._media_get_link()
        _run_until(root, lambda: bar.fake.urls)
        root.update()
        assert bar.fake.urls == ["https://youtu.be/AAAAAAAAAAA"]
        assert editor.media_link_entry.get() == "https://youtu.be/BBBBBBBBBBB"
    finally:
        editor.media_link_entry.delete(0, "end")
        editor.download_bar = None


def test_cancel_stops_a_download(root, download_bar):
    bar = download_bar
    assert bar.cancel_btn.cget("state") == "disabled"
    bar.receive_url("https://youtu.be/AAAAAAAAAAA")
    bar._download()
    assert bar.cancel_btn.cget("state") == "normal"
    bar.cancel_download()
    _run_until(root, lambda: not bar.busy())
    assert bar.status_label.cget("text") == "Download cancelled"
    assert bar.download_btn.cget("state") == "normal"
    assert bar.cancel_btn.cget("state") == "disabled"


def test_a_crashing_download_does_not_wedge_the_bar(root, download_bar, monkeypatch):
    from videokidnapper.ui import source_bar

    def boom(*_a, **_k):
        raise OSError("disk full")

    monkeypatch.setattr(source_bar, "download_video", boom)
    bar = download_bar
    bar.receive_url("https://youtu.be/AAAAAAAAAAA")
    bar._download()
    _run_until(root, lambda: not bar.busy())
    assert "disk full" in bar.status_label.cget("text")


def test_subtitles_after_the_end_are_left_out(editor, tmp_path, monkeypatch):
    """Cues past the end of the video were clamped to zero length at the
    very end: invisible, but counted as imported."""
    from tkinter import filedialog

    srt = tmp_path / "long.srt"
    srt.write_text("1\n00:00:01,000 --> 00:00:02,000\nin\n\n"
                   "2\n00:00:05,500 --> 00:00:08,000\nruns past the end\n\n"
                   "3\n00:00:30,000 --> 00:00:32,000\nafter the end\n", encoding="utf-8")
    monkeypatch.setattr(filedialog, "askopenfilename", lambda **_k: str(srt))
    toasts = []
    monkeypatch.setattr(editor, "_notify", lambda m, level="info": toasts.append((level, m)))
    editor.text_layers._add_layer(preset_data={"text": "already here", "start": 0, "end": 1})
    try:
        editor._import_srt()
        texts = [layer.get_layer_data()["text"] for layer in editor.text_layers.layers]
        assert texts == ["already here", "in", "runs past the end"]
        # The first imported caption is selected, not the one already there.
        assert editor.selected_text_index == 1
        assert "1 after the end" in toasts[-1][1]
    finally:
        editor.text_layers.clear_layers()
        editor.selected_text_index = None
        editor._sync_timeline_clips()


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------

class _QuietExportDialog:
    """Stands in for the export progress window, so no window opens."""

    def __init__(self, *_a, **_k):
        import threading

        self.cancel_event = threading.Event()
        self.result = None

    def winfo_exists(self):
        return True

    def update_progress(self, *_a):
        pass

    def export_complete(self, path):
        self.result = ("done", path)

    def export_failed(self, message):
        self.result = ("failed", message)


def test_every_exported_clip_is_in_history(root, editor, tmp_path, monkeypatch):
    """Three ranges exported without joining wrote three files, but only
    the last one was recorded in History."""
    from pathlib import Path

    from videokidnapper.ui import trim_tab as tt
    from videokidnapper.utils import settings

    def fake_encode(_src, _start, _end, _preset, output_path, **_kw):
        with open(output_path, "wb") as fh:
            fh.write(b"clip")
        return output_path

    dialogs = []
    # Progress shows on the Export page, which this editor has none of.
    from types import SimpleNamespace
    monkeypatch.setattr(editor, "export_progress", SimpleNamespace(
        running=False,
        begin=lambda *a, **k: dialogs.append(_QuietExportDialog()) or dialogs[-1]))
    monkeypatch.setattr(tt, "trim_to_video", fake_encode)
    monkeypatch.setattr(tt, "export_output_ok", lambda *_a, **_k: True)
    settings.clear_history()
    editor.export_options.output_folder_var.set(str(tmp_path / "out"))
    editor.export_options.concat_var.set(False)
    editor.export_options.audio_only_var.set(False)
    editor.format_var.set("MP4")
    editor.range_queue.set_ranges([(0.0, 1.0), (1.5, 2.5)])
    editor._apply_selection(3.0, 4.0)
    try:
        editor._export()
        _run_until(root, lambda: dialogs and dialogs[0].result)
        assert dialogs[0].result[0] == "done"
        written = sorted(p.name for p in (tmp_path / "out").iterdir())
        recorded = sorted(Path(entry["path"]).name for entry in settings.get_history())
        assert len(written) == 3
        assert recorded == written
    finally:
        editor.range_queue.set_ranges([])
        settings.clear_history()
