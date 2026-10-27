# SPDX-FileCopyrightText: 2026 AES256Afro <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Regressions from a bug sweep of the Studio editor and its preview.

Everything here reads widget state; no window is ever shown. The Tk root
is withdrawn as soon as it exists, and canvases that need a size to draw
into are given one (a withdrawn window's widgets report 1 x 1). Real
playback needs a sound device, so the player is replaced by a stand-in
that drives the same callbacks from a worker thread.

Skipped without a display, like the rest of the Tk tests, and the
editor-level tests also need ffmpeg to make a small silent clip.
"""

import shutil
import subprocess
import threading
import time
import tkinter
import types

import pytest

ctk = pytest.importorskip("customtkinter")
Image = pytest.importorskip("PIL.Image")

_HAS_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))
needs_ffmpeg = pytest.mark.skipif(not _HAS_FFMPEG, reason="ffmpeg / ffprobe not on PATH")
E = types.SimpleNamespace


@pytest.fixture(scope="module")
def root():
    try:
        r = ctk.CTk()
    except Exception as exc:  # noqa: BLE001 - headless CI
        pytest.skip(f"no usable display: {type(exc).__name__}")
    r.withdraw()
    yield r
    r.destroy()


def _sized(widget, width, height):
    widget.winfo_width = lambda: width
    widget.winfo_height = lambda: height


def _run_until(root, predicate, timeout=20.0):
    """Run the Tk loop (worker threads post to it) until ``predicate``."""
    end = time.monotonic() + timeout

    def poll():
        if predicate() or time.monotonic() > end:
            root.quit()
            return
        root.after(20, poll)

    root.after(20, poll)
    root.mainloop()
    assert predicate(), "timed out"


# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------

@pytest.fixture
def player(root, monkeypatch):
    from videokidnapper.ui import video_player as vp

    frame = Image.new("RGB", (1280, 720), (0, 0, 0))
    monkeypatch.setattr(vp, "get_frame_at", lambda *_a, **_k: frame)
    p = vp.VideoPlayer(root)
    _sized(p.canvas, 800, 450)
    p.video_path = "fake.mp4"
    p.duration = 10.0
    options, layers, images = {}, [], []
    p.set_export_options_provider(lambda: options)
    p.set_text_layers_provider(lambda: layers)
    p.set_image_layers_provider(lambda: images)
    p.options, p.layers, p.images, p.frame = options, layers, images, frame
    yield p
    p._playing, p._av_player = False, None
    p.destroy()


class _FakeAV:
    """Stands in for AudioVideoPlayer: one frame, then the end of the clip,
    both delivered from a worker thread like the real decode threads."""

    def __init__(self, _path, render_callback, on_finished, **_options):
        self.render, self.finish = render_callback, on_finished
        self.stops = []

    def play(self, start=0.0, end=None):
        def run():
            self.render(Image.new("RGB", (1280, 720)), start + 0.04)
            self.finish("end")
        worker = threading.Thread(target=run)
        worker.start()
        worker.join()

    def current_time(self):
        return 0.0

    def stop(self, wait=0.0):
        self.stops.append(wait)


def test_playing_frames_show_the_export_frame(player, tmp_path):
    """Playback drew the raw source: no rotation, frame shape, crop or
    stickers, and it stayed that way after pausing."""
    sticker = tmp_path / "sticker.png"
    Image.new("RGBA", (40, 40), (255, 0, 0, 255)).save(sticker)
    player.options.update(rotate=90, aspect_preset="9:16")
    player.images.append({"path": str(sticker), "start": 0, "end": 99, "scale": 1.0})

    player.show_frame(1.0)
    paused = (player._layout_size, player._last_frame_rect[4:], player._image_bboxes)
    player._playing, player._av_player = True, object()
    player._av_render_frame(player.frame, 1.5)
    playing = (player._layout_size, player._last_frame_rect[4:], player._image_bboxes)

    assert paused[0] == (720, 1280)
    assert playing == paused


def test_playback_threads_never_call_tk(player, monkeypatch):
    """Frames and the end of the clip are handed over, not pushed with
    winfo_exists/after from the decode threads."""
    from videokidnapper.ui import video_player as vp

    monkeypatch.setattr(vp.playback, "is_available", lambda: True)
    monkeypatch.setattr(vp.playback, "AudioVideoPlayer", _FakeAV)
    off_thread = []
    for name in ("after", "winfo_exists"):
        real = getattr(tkinter.Misc, name)

        def spy(self, *a, _real=real, _name=name, **k):
            if threading.current_thread() is not threading.main_thread():
                off_thread.append(_name)
            return _real(self, *a, **k)
        monkeypatch.setattr(tkinter.Misc, name, spy)

    player.play(start=1.0, end=2.0)

    assert off_thread == []
    assert player.current_time == pytest.approx(1.04)
    assert player._playing is False          # the clip's end was noticed
    assert player._av_player is None


def test_closing_the_window_waits_for_the_audio_thread(root):
    """Closing mid-playback left the sound playing and crashed on exit."""
    from videokidnapper.ui.video_player import VideoPlayer

    p = VideoPlayer(root)
    fake = _FakeAV("clip.mp4", None, None)
    p._playing, p._av_player = True, fake
    p.destroy()
    assert fake.stops and fake.stops[0] > 0


def test_a_finished_crop_still_shapes_the_preview(player):
    """Outside crop mode the preview ignored the crop and laid captions
    out on the whole frame; the export puts them inside the crop."""
    player.layers.append({"text": "HELLO", "fontsize": 24, "start": 0, "end": 99,
                          "position": "(w-tw)/2:h-th-20"})
    player.set_crop({"x": 600, "y": 100, "w": 400, "h": 400})
    assert not player._crop_mode
    player.show_frame(1.0)
    assert player._layout_size == (400, 400)
    assert player._layout_offset == (600, 100)
    (_idx, _x1, _y1, x2, y2), = player._text_bboxes
    assert x2 <= 400 and y2 <= 400


# ---------------------------------------------------------------------------
# Timeline
# ---------------------------------------------------------------------------

def test_dragging_an_edge_on_a_zoomed_timeline_follows_the_mouse(root):
    """Zoomed in, the view re-centred on the dragged edge every motion
    event, so dragging the in point right sent it left."""
    from videokidnapper.ui.studio.timeline import HEADER_W, TimelineView, lane_top

    tl = TimelineView(root)
    _sized(tl.canvas, 1400, 260)
    tl.duration = 20.0
    tl.set_selection(8.0, 12.0)
    tl.playhead = 10.0
    tl.set_zoom(4.0)                      # 5 s visible: 7.5 to 12.5
    y = lane_top("video")[0] + 10
    x = tl._t2x(8.0)

    tl._on_press(E(x=x, y=y))
    seen = []
    for step in range(1, 7):
        tl._on_motion(E(x=x + 10 * step, y=y))
        seen.append(tl.sel_start)
    tl._on_release(E(x=x + 60, y=y))
    tl.destroy()

    px_per_second = (1400 - HEADER_W - 8) / 5.0
    assert seen == sorted(seen)
    assert seen[-1] == pytest.approx(8.0 + 60 / px_per_second, abs=0.02)


# ---------------------------------------------------------------------------
# The editor
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def clip(tmp_path_factory):
    """6 s test pattern, 320x180, with a silent audio track."""
    if not _HAS_FFMPEG:
        pytest.skip("ffmpeg / ffprobe not on PATH")
    path = tmp_path_factory.mktemp("clip") / "clip.mp4"
    subprocess.run([
        "ffmpeg", "-v", "error", "-y",
        "-f", "lavfi", "-i", "testsrc=size=320x180:rate=24:duration=6",
        "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
        "-t", "6", "-c:v", "libx264", "-preset", "ultrafast",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path),
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
    _sized(ed.player.canvas, 640, 360)
    yield ed
    ed._project_dirty = False
    ed.destroy()
    mp.undo()


def test_dragging_a_sticker_moves_that_sticker(editor, tmp_path):
    """With an earlier sticker's file missing, dragging the visible one
    moved the missing one and selected it in the Inspector."""
    sticker = tmp_path / "logo.png"
    Image.new("RGBA", (60, 40), (255, 0, 0, 255)).save(sticker)
    panel = editor.image_layers
    gone = panel.add_layer_from_path(str(tmp_path / "moved-away.png"))
    real = panel.add_layer_from_path(str(sticker))
    for layer in panel.layers:
        layer.time_slider.set_values(0, 6)
    try:
        editor.player.show_frame(1.0)
        (index, *_box), = editor.player._image_bboxes
        assert panel.layers[index] is real
        editor._on_image_dragged(index, 33, 44)
        assert (real.x_var.get(), real.y_var.get()) == (33, 44)
        assert (gone.x_var.get(), gone.y_var.get()) == (-1, -1)
        assert editor.selected_image_index == 1
    finally:
        panel.clear_layers()
        editor.selected_image_index = None


def test_auto_track_keeps_the_caption_style(editor):
    """Installing the tracked path reset the caption to the Subtitle look."""
    layer = editor.add_text_layer()
    try:
        layer.style_var.set("Title")
        layer._on_style_change("Title")
        layer.size_var.set("64")
        layer.color_var.set("Yellow")
        layer.outline_var.set(True)
        layer.shadow_var.set(True)
        keep = ("fontsize", "fontcolor", "box", "borderw", "shadowx", "position")
        before = {k: layer.get_layer_data()[k] for k in keep}
        editor.text_layers.set_layer_keyframes(
            0, [{"t": 0.0, "x": 10, "y": 10}, {"t": 1.0, "x": 90, "y": 40}])
        after = layer.get_layer_data()
        assert {k: after[k] for k in keep} == before
        assert len(after["keyframes"]) == 2
    finally:
        editor.delete_layer("text", 0)


def test_hidden_export_page_is_not_rebuilt_on_every_edit(root, editor):
    """Each in/out drag event rebuilt the Export page's range list, a
    second per event with ten saved ranges, while it was not even shown."""
    from videokidnapper.ui.studio.export_workspace import ExportWorkspace

    showing = {"workspace": "edit"}
    app = types.SimpleNamespace(
        workspaces=types.SimpleNamespace(get=lambda: showing["workspace"]),
        show_workspace=lambda _key: None,
    )
    page = ExportWorkspace(root, app, editor)
    try:
        before = page.ranges_box.winfo_children()
        editor.range_queue.set_ranges([(0.5, 1.0), (2.0, 3.0)])
        assert page.ranges_box.winfo_children() == before
        showing["workspace"] = "export"
        page.refresh()
        assert len(page.ranges_box.winfo_children()) == 2
    finally:
        editor.range_queue.set_ranges([])
        page.destroy()


def test_mark_keys_never_make_an_empty_selection(editor):
    """O at 0:00, or I at the very end, made a zero-length selection that
    exported as a file with no picture."""
    from videokidnapper.ui.trim_tab import MIN_SELECTION_S

    duration = editor.video_info["duration"]
    try:
        editor._seek(0.0)
        editor.keyboard_mark_out()
        start, end = editor.timeline.get_values()
        assert start == 0.0 and end - start >= MIN_SELECTION_S - 1e-9

        editor._apply_selection(0.0, duration)
        editor._seek(duration)
        editor.keyboard_mark_in()
        start, end = editor.timeline.get_values()
        assert end == pytest.approx(duration)
        assert end - start >= MIN_SELECTION_S - 1e-9
    finally:
        editor._apply_selection(0.0, duration)


def test_a_shorter_video_clamps_the_restored_ranges(editor):
    """A project relinked to a shorter video kept an Out point past the end
    and saved ranges that held nothing."""
    from videokidnapper.utils.time_format import seconds_to_hms

    duration = editor.video_info["duration"]
    snap = editor._snapshot()
    snap.update(range=(2.0, 15.0), queued=[(1.0, 2.0), (10.0, 14.0)])
    try:
        editor._apply_snapshot(snap)
        assert editor.timeline.get_values() == (2.0, duration)
        assert editor.end_entry.get_value() == seconds_to_hms(duration)
        assert editor.range_queue.get_ranges() == [(1.0, 2.0)]
    finally:
        editor.range_queue.set_ranges([])
        editor._apply_selection(0.0, duration)


@needs_ffmpeg
def test_an_empty_export_is_a_failure(clip, tmp_path):
    """ffmpeg exits cleanly on a range with no frames and leaves a stub."""
    from videokidnapper.ui.trim_tab import export_output_ok

    sound_only = tmp_path / "sound-only.mp4"
    subprocess.run([
        "ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "anullsrc",
        "-t", "0.05", "-c:a", "aac", str(sound_only),
    ], check=True, capture_output=True, timeout=60)
    stub = tmp_path / "stub.mp4"
    stub.write_bytes(b"\0" * 262)

    assert export_output_ok(clip)
    assert not export_output_ok(sound_only)
    assert export_output_ok(sound_only, audio_only=True)
    assert not export_output_ok(stub)
    assert not export_output_ok(tmp_path / "missing.mp4")


class _Dialog:
    """Stand-in for the export progress job the Export page hands out."""

    def __init__(self, *_a, **_k):
        self.cancel_event = threading.Event()
        self.done = self.failed = None

    def winfo_exists(self):
        return True

    def update_progress(self, *_a):
        pass

    def export_complete(self, path):
        self.done = path

    def export_failed(self, message):
        self.failed = message


def test_export_keeps_to_the_video_it_started_with(root, editor, clip, tmp_path, monkeypatch):
    """A file opened mid-export (Ctrl+O still worked) supplied the clips
    still to come, and the worker updated widgets from its own thread."""
    from videokidnapper.ui import trim_tab as tt

    original = editor.video_path
    inputs = []

    def fake_trim(path, start, end, preset, output_path, **_kw):
        inputs.append(path)
        editor.video_path = str(tmp_path / "opened-meanwhile.mp4")
        shutil.copy(clip, output_path)
        return output_path

    dialogs = []
    monkeypatch.setattr(editor.export_progress, "begin",
                        lambda *a, **k: dialogs.append(_Dialog()) or dialogs[-1])
    monkeypatch.setattr(tt, "trim_to_video", fake_trim)
    notified_from = []
    monkeypatch.setattr(editor, "_notify",
                        lambda *_a: notified_from.append(threading.current_thread()))
    editor.format_var.set("MP4")
    editor.options.audio_only_var.set(False)
    editor.options.concat_var.set(False)
    editor.options.output_folder_var.set(str(tmp_path / "out"))
    editor.range_queue.set_ranges([(0.5, 1.0)])
    try:
        editor._export()
        _run_until(root, lambda: dialogs[0].done or dialogs[0].failed)
    finally:
        editor.video_path = original
        editor.range_queue.set_ranges([])

    assert inputs == [original, original]
    assert dialogs[0].done and not dialogs[0].failed
    assert notified_from and all(t is threading.main_thread() for t in notified_from)


def test_captions_for_another_video_are_dropped(editor):
    """Transcription finishing after another video was opened added the
    old video's captions to the new one."""
    before = len(editor.text_layers.layers)
    editor._on_captions_done([{"start": 1.0, "end": 2.0, "text": "old words"}],
                             "C:/elsewhere/old.mp4")
    assert len(editor.text_layers.layers) == before
    assert str(editor.captions_btn.cget("state")) == "normal"


def test_shortcuts_wait_while_a_dialog_holds_the_grab():
    """The export window grabs input, but bind_all shortcuts still ran."""
    from videokidnapper.app import App

    opened = []
    dialog = types.SimpleNamespace()
    dialog.winfo_toplevel = lambda: dialog
    fake = types.SimpleNamespace(
        trim_tab=types.SimpleNamespace(keyboard_open=lambda: opened.append(True)),
        workspaces=types.SimpleNamespace(get=lambda: "edit"),
        grab_current=lambda: dialog,
        _editing_in_entry=lambda _event: False,
    )
    fake._modal_open = lambda: App._modal_open(fake)

    assert App._shortcut(fake, E(widget=None), "keyboard_open") is None
    assert opened == []
    fake.grab_current = lambda: None
    assert App._shortcut(fake, E(widget=None), "keyboard_open") == "break"
    assert opened == [True]
