# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Cancelling an encode must work even when ffmpeg goes quiet.

``_parse_progress`` reads ffmpeg's stderr with a blocking ``readline()``
and, until 1.8.1, only checked the cancel flag *after* a line arrived.
An ffmpeg that stalled — an unresponsive network source, a filter chain
grinding on one frame — emitted nothing, so Stop did nothing until the
process happened to move on by itself.

``concat.py`` already had this right (``_wait_for_concat`` drains stderr
on a thread and polls with a timeout). These tests pin the same
behaviour for the encode path.
"""

import subprocess
import sys
import threading
import time

from videokidnapper.core.ffmpeg._internals import _parse_progress, was_cancelled


def _silent_process(seconds=30):
    """A child that holds stderr open and never writes to it."""
    return subprocess.Popen(
        [sys.executable, "-c", f"import time; time.sleep({seconds})"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )


def test_cancel_interrupts_a_silent_ffmpeg():
    """The regression: cancel must not wait on ffmpeg's next stderr line."""
    process = _silent_process()
    cancel = threading.Event()
    threading.Timer(0.3, cancel.set).start()

    started = time.monotonic()
    _parse_progress(process, duration=10.0, callback=None, cancel_event=cancel)
    elapsed = time.monotonic() - started

    process.wait(timeout=5)
    # Without the watchdog this blocks for the child's full 30s sleep.
    assert elapsed < 5.0, f"cancel took {elapsed:.1f}s — watchdog not firing"
    assert process.poll() is not None, "process was not killed"


def test_normal_completion_is_not_delayed():
    """A clean run must not pay the watchdog's poll interval on exit."""
    process = subprocess.Popen(
        [sys.executable, "-c", "import sys; sys.stderr.write('done\\n')"],
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
    )
    cancel = threading.Event()  # never set

    started = time.monotonic()
    tail = _parse_progress(process, duration=1.0, callback=None, cancel_event=cancel)
    elapsed = time.monotonic() - started
    process.wait(timeout=5)

    assert "done" in tail
    assert elapsed < 2.0, f"clean exit took {elapsed:.1f}s"


def test_progress_still_parsed():
    """The watchdog must not disturb normal progress reporting."""
    script = (
        "import sys\n"
        "sys.stderr.write('frame=1 time=00:00:05.00 bitrate=1\\n')\n"
        "sys.stderr.write('some diagnostic line\\n')\n"
    )
    process = subprocess.Popen(
        [sys.executable, "-c", script],
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
    )
    seen = []
    tail = _parse_progress(process, 10.0, seen.append, threading.Event())
    process.wait(timeout=5)

    assert seen == [0.5], f"expected 50% progress, got {seen}"
    assert "some diagnostic line" in tail
    assert "time=00:00:05.00" not in tail, "progress lines must not pollute the tail"


def test_no_cancel_event_still_works():
    """cancel_event=None is a supported call shape (no watchdog started)."""
    process = subprocess.Popen(
        [sys.executable, "-c", "import sys; sys.stderr.write('x\\n')"],
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
    )
    tail = _parse_progress(process, 1.0, None, None)
    process.wait(timeout=5)
    assert "x" in tail


def test_was_cancelled_helper():
    assert was_cancelled(None) is False
    event = threading.Event()
    assert was_cancelled(event) is False
    event.set()
    assert was_cancelled(event) is True
