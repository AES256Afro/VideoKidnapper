# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Waiting for a worker thread from the Tk main thread."""

import time


def wait_for_thread(widget, thread, timeout):
    """Wait up to ``timeout`` seconds for ``thread`` while Tk keeps running.

    A plain ``join()`` would freeze the event loop, and the export workers
    still hand calls such as ``winfo_exists()`` to the main thread. Joined,
    they wait on each other until the timeout. Pumping events in between
    lets the worker finish.
    """
    if thread is None:
        return
    deadline = time.monotonic() + timeout
    while thread.is_alive() and time.monotonic() < deadline:
        try:
            widget.update()
        except Exception:
            # The window is already going away; just wait it out.
            pass
        thread.join(0.05)
