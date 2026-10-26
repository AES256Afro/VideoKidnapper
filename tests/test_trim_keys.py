# SPDX-FileCopyrightText: 2026 AES256Afro <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Keys and buttons for trimming, and getting the keyboard back from a text box."""

import shutil
import subprocess
import types

import pytest

ctk = pytest.importorskip("customtkinter", reason="needs customtkinter")

from videokidnapper import app as app_module  # noqa: E402

E = types.SimpleNamespace
_HAS_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


@pytest.fixture(scope="module")
def root():
    try:
        r = ctk.CTk()
    except Exception as exc:  # pragma: no cover - headless CI
        pytest.skip(f"no usable display: {type(exc).__name__}: {exc}")
    r.withdraw()
    yield r
    r.destroy()


# ---------------------------------------------------------------------------
# Focus: a click outside the text box, or Esc, gives the keys back
# ---------------------------------------------------------------------------

def _widget(cls):
    return E(winfo_class=lambda: cls)


class _FakeApp:
    _release_text_focus = app_module.App._release_text_focus
    _escape_shortcut = app_module.App._escape_shortcut
    _editing_in_entry = app_module.App._editing_in_entry

    def __init__(self, focused):
        self.focused = focused
        self.focus_calls = 0
        self.workspaces = E(get=lambda: "edit")

    def focus_get(self):
        return self.focused

    def focus_set(self):
        self.focus_calls += 1
        self.focused = None


@pytest.mark.parametrize("clicked", ["Canvas", "Frame", "Label", "Button"])
def test_clicking_outside_the_caption_box_takes_the_keyboard_back(clicked):
    app = _FakeApp(focused=_widget("Text"))
    app._release_text_focus(E(widget=_widget(clicked)))
    assert app.focus_calls == 1


def test_clicking_into_another_text_box_leaves_focus_to_it():
    app = _FakeApp(focused=_widget("Text"))
    app._release_text_focus(E(widget=_widget("Entry")))
    assert app.focus_calls == 0


def test_clicks_do_nothing_when_no_text_box_has_the_keyboard():
    app = _FakeApp(focused=_widget("Canvas"))
    app._release_text_focus(E(widget=_widget("Canvas")))
    assert app.focus_calls == 0


def test_escape_in_a_text_box_leaves_it():
    app = _FakeApp(focused=_widget("Entry"))
    assert app._escape_shortcut(E(widget=_widget("Entry"))) == "break"
    assert app.focus_calls == 1


def test_escape_elsewhere_is_left_alone():
    app = _FakeApp(focused=None)
    assert app._escape_shortcut(E(widget=_widget("Canvas"))) is None
    assert app.focus_calls == 0


def test_tk_emacs_keys_are_removed_from_text_boxes(root):
    app_module.App._drop_tk_text_keys(E(bind_class=root.bind_class))
    for cls in ("Text", "Entry"):
        for seq in ("<Control-Key-o>", "<Control-Key-k>", "<Control-Key-d>",
                    "<Control-Key-t>"):
            assert not root.bind_class(cls, seq).strip()
    # Select all stays.
    assert root.tk.call("event", "info", "<<SelectAll>>")


# ---------------------------------------------------------------------------
# The editor
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def clip(tmp_path_factory):
    """4 s test pattern at 25 fps."""
    if not _HAS_FFMPEG:
        pytest.skip("ffmpeg / ffprobe not on PATH")
    path = tmp_path_factory.mktemp("clip") / "clip.mp4"
    subprocess.run([
        "ffmpeg", "-v", "error", "-y",
        "-f", "lavfi", "-i", "testsrc=size=160x90:rate=25:duration=4",
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

    ed = TrimTab(root, E(show_workspace=lambda _key: None))
    ed.pack(fill="both", expand=True)
    assert ed._load_path(str(clip))
    yield ed
    ed._project_dirty = False
    ed.destroy()
    mp.undo()


def test_arrow_keys_step_one_frame(editor):
    editor._seek(2.0)
    editor.keyboard_step_frame(1)
    assert editor.playhead == pytest.approx(2.04, abs=1e-6)
    editor.keyboard_step_frame(-1)
    editor.keyboard_step_frame(-1)
    assert editor.playhead == pytest.approx(1.96, abs=1e-6)


def test_the_bar_says_what_is_kept_and_whole_video_resets_it(editor):
    assert "whole video" in editor.keep_label.cget("text")
    assert editor.whole_video_btn.cget("state") == "disabled"

    editor._seek(1.0)
    editor.keyboard_mark_in()
    editor._seek(2.5)
    editor.keyboard_mark_out()
    text = editor.keep_label.cget("text")
    assert "0:01.0 – 0:02.5" in text and "1.5 s" in text
    assert editor.whole_video_btn.cget("state") == "normal"

    editor.reset_selection()
    assert editor.timeline.get_values() == (0.0, editor.video_info["duration"])
    assert "whole video" in editor.keep_label.cget("text")
    # Undo brings the trim back.
    editor.keyboard_undo()
    assert editor.timeline.get_values() == pytest.approx((1.0, 2.5), abs=0.01)
    editor.reset_selection()


def test_dragging_a_handle_updates_the_bar(editor):
    editor._on_timeline_selection(0.5, 3.0)
    assert "0:00.5 – 0:03.0" in editor.keep_label.cget("text")
    editor.reset_selection()


def test_delete_removes_the_caption_picked_on_the_timeline(editor):
    editor.add_text_layer()
    assert len(editor.text_layers.layers) == 1
    editor.timeline.set_selected("text", 0)
    editor.keyboard_delete()
    assert editor.text_layers.layers == []
    editor.keyboard_undo()
    assert len(editor.text_layers.layers) == 1
    editor.delete_layer("text", 0)


def test_delete_with_nothing_picked_does_nothing(editor):
    editor.add_text_layer()
    editor.timeline.set_selected(None, 0)
    editor.keyboard_delete()
    assert len(editor.text_layers.layers) == 1
    editor.delete_layer("text", 0)


# ---------------------------------------------------------------------------
# Hover hints and panels that fit
# ---------------------------------------------------------------------------

def test_icon_buttons_say_what_they_do_in_the_status_bar(root):
    from videokidnapper.ui.studio import icons
    from videokidnapper.ui.widgets import Toast

    # Enter and Leave only reach a mapped window; conftest keeps this one
    # invisible and off screen.
    top = ctk.CTkToplevel(root)
    bar = Toast(top)
    icons.set_hint_handler(bar.show_hint)
    try:
        bar.show("Saved range 1", "success")
        btn = icons.icon_button(top, "crop", hint="Crop the picture by hand")
        btn.pack()
        top.update()
        btn._canvas.event_generate("<Enter>")
        assert bar._label.cget("text") == "Crop the picture by hand"
        btn._canvas.event_generate("<Leave>")
        assert bar._label.cget("text") == "Saved range 1"
        # A real message during the hover isn't undone when the mouse leaves.
        btn._canvas.event_generate("<Enter>")
        bar.show("Exported 1 clip", "success")
        btn._canvas.event_generate("<Leave>")
        assert bar._label.cget("text") == "Exported 1 clip"
    finally:
        icons.set_hint_handler(None)
        top.destroy()


# The Inspector has about 515 px for a page in a 1440x900 window. The Text
# page needed 688, so its bottom half was always behind a scrollbar.
_INSPECTOR_ROOM = 510


def _unscaled_height(widget):
    from customtkinter import ScalingTracker

    widget.update_idletasks()
    return widget.winfo_reqheight() / ScalingTracker.get_widget_scaling(widget)


def test_the_text_page_fits_without_scrolling(editor):
    editor.add_text_layer()
    try:
        page = editor.inspector.pages["text"]
        page.refresh()
        assert _unscaled_height(page.form) <= _INSPECTOR_ROOM
    finally:
        editor.delete_layer("text", 0)


def test_the_clip_page_fits_without_scrolling(editor):
    page = editor.inspector.pages["clip"]
    total = sum(_unscaled_height(child) for child in page.winfo_children()) + 10 * 5
    assert total <= _INSPECTOR_ROOM
