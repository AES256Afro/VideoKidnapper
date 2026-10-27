# SPDX-FileCopyrightText: 2026 AES256Afro <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""The Debug log takes lines from any thread without touching Tk there.

stdout and stderr are routed into the Debug log, so a worker thread that
prints, warns or fails ends up in ``add_log``. It used to call
``winfo_exists()`` and ``after()`` on that thread, and Tk used off the
main thread can hang or crash the whole app.
"""

import sys
import threading

import pytest

ctk = pytest.importorskip("customtkinter", reason="needs customtkinter")

from videokidnapper.ui.debug_tab import DebugTab  # noqa: E402


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


@pytest.fixture
def page(root):
    tab = DebugTab(root, app=None)
    yield root, tab
    tab.destroy()
    sys.stdout, sys.stderr = sys.__stdout__, sys.__stderr__


def _text(tab):
    return tab.log_text.get("1.0", "end")


def test_a_worker_thread_never_calls_tk(page, monkeypatch):
    root, tab = page
    tk_threads = []
    for name in ("after", "after_idle", "winfo_exists"):
        real = getattr(tab, name)

        def spy(*args, _real=real, **kwargs):
            tk_threads.append(threading.current_thread())
            return _real(*args, **kwargs)

        monkeypatch.setattr(tab, name, spy)

    worker = threading.Thread(target=lambda: tab.add_log("from a worker", "ERROR"))
    worker.start()
    worker.join()

    assert worker not in tk_threads
    assert "from a worker" not in _text(tab)
    tab._flush()
    assert "from a worker" in _text(tab)


def test_printing_from_a_worker_reaches_the_page(page):
    root, tab = page
    # pytest swaps stdout between setup and the test; capture it again.
    tab._install_log_capture()
    worker = threading.Thread(target=lambda: print("decoder says hi"))
    worker.start()
    worker.join()
    tab._flush()
    assert "decoder says hi" in _text(tab)


def test_the_page_keeps_only_the_newest_lines(page, monkeypatch):
    root, tab = page
    monkeypatch.setattr(DebugTab, "MAX_LINES", 50)
    for i in range(120):
        tab.add_log(f"line {i}")
    tab._flush()
    text = _text(tab)
    assert "line 119" in text and "line 10\n" not in text
    assert int(tab.log_text._textbox.index("end-1c").split(".")[0]) <= 51
