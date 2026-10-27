# SPDX-FileCopyrightText: 2026 AES256Afro <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""The real App, a real clip: trim with the keys, play, pause, close.

The path that crashed 1.9.1: pressing Play opened a console window over
the editor, and pausing crashed inside the sound library. The sound
device is faked so nothing is audible; ffmpeg runs for real, and every
process playback starts must be hidden.
"""

import shutil
import subprocess
import sys
import time
import types

import pytest


def _clip(tmp_path):
    path = tmp_path / "smoke.mp4"
    subprocess.run([
        "ffmpeg", "-v", "error", "-y",
        "-f", "lavfi", "-i", "testsrc=size=640x360:rate=25:duration=6",
        "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
        "-t", "6", "-c:v", "libx264", "-preset", "ultrafast",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path),
    ], check=True, capture_output=True, timeout=60)
    return path


class _SilentStream:
    def __init__(self, **_k):
        pass

    def start(self):
        pass

    def write(self, _data):
        time.sleep(1024 / 44100)

    def stop(self):
        pass

    def abort(self):
        pass

    def close(self):
        pass


def _pump(app, seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.update()
        time.sleep(0.01)


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="needs ffmpeg")
def test_real_app_plays_pauses_and_closes(tmp_path, monkeypatch):
    import tkinter

    # Like the other window tests: skipped where there is no display
    # (the Linux CI runners), checked before anything is set up.
    try:
        tkinter.Tk().destroy()
    except tkinter.TclError as exc:
        pytest.skip(f"no usable display: {exc}")

    from videokidnapper.utils import settings, crash_log
    settings.set("auto_update_check", False)
    crash_log.start("smoke", path=tmp_path / "crash.log")

    monkeypatch.setitem(sys.modules, "sounddevice",
                        types.SimpleNamespace(OutputStream=_SilentStream))
    from videokidnapper.core import playback
    real_popen = subprocess.Popen
    launches = []

    def recording_popen(cmd, *a, **k):
        flags = k.get("creationflags") or 0
        info = k.get("startupinfo")
        hidden = bool(flags & getattr(subprocess, "CREATE_NO_WINDOW", 0)) or bool(
            info is not None and info.dwFlags & subprocess.STARTF_USESHOWWINDOW
            and info.wShowWindow == 0)
        launches.append((" ".join(map(str, cmd)), hidden, k.get("stdin")))
        return real_popen(cmd, *a, **k)

    monkeypatch.setattr(playback.subprocess, "Popen", recording_popen)

    from videokidnapper.app import App
    app = App()
    try:
        _pump(app, 0.5)
        ed = app.trim_tab
        assert ed._load_path(str(_clip(tmp_path)))
        _pump(app, 1.5)
        assert "whole video" in ed.keep_label.cget("text")

        # Trim with the keys, as the user would.
        E = types.SimpleNamespace
        app.show_workspace("edit")
        ed._seek(1.0)
        app._shortcut(E(widget=app), "keyboard_mark_in")
        for _ in range(25):
            app._shortcut(E(widget=app), "keyboard_step_frame", 1)
        assert abs(ed.playhead - 2.0) < 1e-6
        ed._seek(4.0)
        app._shortcut(E(widget=app), "keyboard_mark_out")
        assert "0:01.0 – 0:04.0" in ed.keep_label.cget("text")

        # Play: sound decoder starts hidden, frames arrive, playhead moves.
        ed._seek(1.0)
        launches.clear()
        ed._toggle_play()
        _pump(app, 1.2)
        assert ed.player._playing
        assert ed.playhead > 1.3, ed.playhead
        assert launches
        if sys.platform == "win32":
            assert all(hidden for _cmd, hidden, _in in launches), launches
        sound = [launch for launch in launches if "s16le" in launch[0]]
        assert sound and all(stdin == subprocess.DEVNULL for _c, _h, stdin in sound)

        # Pause, play, pause quickly: no crash, one poll loop, sound closed.
        ed._toggle_play()
        ed._toggle_play()
        ed._toggle_play()
        _pump(app, 0.5)
        assert not ed.player._playing
        playback.wait_for_sound(5.0)
        assert not playback._AUDIO_THREADS

        # Let it play to the out point and stop by itself.
        ed._seek(3.5)
        ed._toggle_play()
        _pump(app, 1.5)
        assert not ed.player._playing
        assert ed.playhead >= 3.9, ed.playhead

        log_text = "\n".join(m for _t, _l, m in app.debug_tab._logs)
        assert "Uncaught exception" not in log_text, log_text
    finally:
        ed._project_dirty = False
        app.destroy()
        crash_log.finish()
    assert "clean exit" in (tmp_path / "crash.log").read_text(encoding="utf-8")
