# SPDX-FileCopyrightText: 2026 AES256Afro <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""A log file that survives the app closing unexpectedly.

The Debug log page lives in memory, so when the app crashed to the
desktop nothing was left to say why. This keeps a small file instead:

- ``faulthandler`` writes the Python stack of every thread into it on a
  hard crash (an access violation in a native library, a Tcl panic).
- Uncaught Python errors, from the Tk loop or any thread, are appended.
- Each run starts with a ``start`` line and ends with a ``clean exit``
  line, so the next run can tell the last one ended unexpectedly.

The file is trimmed to the last few runs, so it never grows large.
"""

import faulthandler
import os
import threading
import time
import traceback
from pathlib import Path


LOG_PATH = Path.home() / ".videokidnapper_crash.log"
START = "=== start"
CLEAN_EXIT = "=== clean exit"
MAX_BYTES = 256 * 1024

_lock = threading.Lock()
_file = None
_previous_crash = ""


def _stamp():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def last_run_crashed(text):
    """True when the last run in ``text`` started but never exited cleanly."""
    start = text.rfind(START)
    if start < 0:
        return False
    return CLEAN_EXIT not in text[start:]


def last_run(text):
    """The log of the last run in ``text``, from its start line on."""
    start = text.rfind(START)
    return text[start:] if start >= 0 else ""


def _trimmed(text, limit=MAX_BYTES):
    """Drop whole runs from the front until ``text`` fits in ``limit``."""
    while len(text.encode("utf-8", errors="replace")) > limit:
        cut = text.find(START, len(START))
        if cut < 0:
            return text[-limit:]
        text = text[cut:]
    return text


def start(version, path=None):
    """Open the log for this run. Returns the last run's log if it crashed.

    Never raises: a log that can't be written must not stop the app.
    """
    global _file, _previous_crash, LOG_PATH
    if path is not None:
        LOG_PATH = Path(path)
    crashed = ""
    try:
        previous = LOG_PATH.read_text(encoding="utf-8", errors="replace")
    except OSError:
        previous = ""
    if last_run_crashed(previous):
        crashed = last_run(previous)
    _previous_crash = crashed
    try:
        kept = _trimmed(previous, MAX_BYTES // 2)
        with open(LOG_PATH, "w", encoding="utf-8") as f:
            f.write(kept)
            if kept and not kept.endswith("\n"):
                f.write("\n")
            f.write(f"{START} {_stamp()} v{version} pid {os.getpid()}\n")
        # Kept open for the life of the process: faulthandler writes to
        # the raw file descriptor while the process is dying.
        _file = open(LOG_PATH, "a", encoding="utf-8")
        faulthandler.enable(file=_file, all_threads=True)
    except Exception:
        _file = None
    return crashed


def previous_crash():
    """The log of the last run if it ended unexpectedly, else ``""``."""
    return _previous_crash


def write(text):
    """Append ``text`` to this run's log. Safe from any thread."""
    with _lock:
        if _file is None:
            return
        try:
            _file.write(f"[{_stamp()}] {text.rstrip()}\n")
            _file.flush()
        except Exception:
            pass


def record_exception(exc_type, exc_value, tb, where=""):
    text = "".join(traceback.format_exception(exc_type, exc_value, tb))
    write(f"Uncaught exception{f' in {where}' if where else ''}:\n{text}")


def install_thread_hook():
    """Log uncaught errors in worker threads too, then do what Python did."""
    previous = threading.excepthook

    def hook(args):
        if args.exc_type is not SystemExit:
            name = getattr(args.thread, "name", "a thread")
            record_exception(args.exc_type, args.exc_value, args.exc_traceback,
                             where=name)
        previous(args)

    threading.excepthook = hook


def finish():
    """Mark this run as having ended cleanly."""
    global _file
    with _lock:
        if _file is None:
            return
        try:
            faulthandler.disable()
            _file.write(f"{CLEAN_EXIT} {_stamp()}\n")
            _file.close()
        except Exception:
            pass
        _file = None
