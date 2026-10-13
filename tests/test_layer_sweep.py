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

    started = time.perf_counter()
    editor._import_srt()
    editor.update()
    elapsed = time.perf_counter() - started
    try:
        assert len(editor.text_layers.layers) == 300
        assert toasts[-1][0] == "success", toasts
        assert elapsed < 1.0, f"import took {elapsed:.2f}s"
    finally:
        editor.text_layers.clear_layers()
        editor.selected_text_index = None
        editor._sync_timeline_clips()
