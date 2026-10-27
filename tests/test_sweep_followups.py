# SPDX-FileCopyrightText: 2026 AES256Afro <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Follow-ups from the crash and correctness review.

- A failed or stopped join left its half-written file behind.
- The update check called Tk from its worker thread.
"""

import io
import threading

import pytest

from videokidnapper.core.ffmpeg import concat


class _FakeJoin:
    """An ffmpeg join that writes some of its output, then exits ``code``."""

    def __init__(self, output, code, hang=False):
        output.write_bytes(b"partial")
        self.stderr = io.StringIO("")
        self.returncode = None
        self._code = code
        self._hang = hang

    def wait(self, timeout=None):
        if self._hang:
            import subprocess
            raise subprocess.TimeoutExpired("ffmpeg", timeout)
        self.returncode = self._code
        return self._code

    def kill(self):
        self._hang = False
        self._code = -9


@pytest.fixture
def clips(tmp_path):
    paths = []
    for i in range(2):
        p = tmp_path / f"clip{i}.mp4"
        p.write_bytes(b"x")
        paths.append(str(p))
    return paths


def test_a_failed_join_leaves_no_file(tmp_path, clips, monkeypatch):
    out = tmp_path / "joined.mp4"
    monkeypatch.setattr(concat.subprocess, "Popen",
                        lambda *a, **k: _FakeJoin(out, 1))
    assert concat.concat_clips(clips, str(out)) is None
    assert not out.exists()


def test_a_stopped_join_leaves_no_file(tmp_path, clips, monkeypatch):
    out = tmp_path / "joined.mp4"
    monkeypatch.setattr(concat.subprocess, "Popen",
                        lambda *a, **k: _FakeJoin(out, 0, hang=True))
    stop = threading.Event()
    stop.set()
    assert concat.concat_clips(clips, str(out), cancel_event=stop) is None
    assert not out.exists()


def test_a_good_join_keeps_its_file(tmp_path, clips, monkeypatch):
    out = tmp_path / "joined.mp4"
    monkeypatch.setattr(concat.subprocess, "Popen",
                        lambda *a, **k: _FakeJoin(out, 0))
    assert concat.concat_clips(clips, str(out)) == str(out)
    assert out.exists()


def test_the_update_check_never_calls_tk_from_its_thread(monkeypatch):
    from videokidnapper import app as app_module

    tk_threads, shown, said, pending = [], [], [], []

    class FakeApp:
        _run_update_check = app_module.App._run_update_check

        def after(self, _ms, fn, *args):
            tk_threads.append(threading.current_thread())
            pending.append((fn, args))

        def winfo_exists(self):
            tk_threads.append(threading.current_thread())
            return True

        def _show_update_chip(self, tag, link):
            shown.append((tag, link))

    def check_async(_version, on_update, on_done=None):
        def worker():
            on_update("v9.9.9", "https://example.invalid/release")
            on_done("newer")
        t = threading.Thread(target=worker, name="update-check")
        t.start()
        t.join()

    monkeypatch.setattr(app_module, "check_async", check_async)
    FakeApp()._run_update_check(said.append)
    assert all(t is threading.main_thread() for t in tk_threads)
    # The Tk thread's poll picks the answer up.
    while pending:
        fn, args = pending.pop(0)
        fn(*args)
    assert shown == [("v9.9.9", "https://example.invalid/release")]
    assert said == ["newer"]
