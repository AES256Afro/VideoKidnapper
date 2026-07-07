# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
import os
import shutil
import subprocess
import sys
from pathlib import Path


def _bundled_candidates(binary_name):
    """Places a bundled ffmpeg/ffprobe may live, in priority order.

    - Next to the app executable when frozen (PyInstaller). This is how
      the MSIX package ships ffmpeg: PATH inside the MSIX container is
      unreliable (the activation broker does not rebuild it from the
      registry), so PATH-based discovery cannot be the only route.
    - The repo/_MEIPASS-relative ``assets/ffmpeg/bin`` dir — the
      historical location the Setup dialog installs into for source
      checkouts.
    """
    exe = f"{binary_name}.exe" if os.name == "nt" else binary_name
    roots = []
    if getattr(sys, "frozen", False):
        roots.append(Path(sys.executable).resolve().parent)
    roots.append(Path(__file__).resolve().parent.parent.parent)
    for root in roots:
        yield root / "assets" / "ffmpeg" / "bin" / exe
        yield root / exe


def _find_binary(binary_name):
    found = shutil.which(binary_name)
    if found:
        return Path(found)
    for candidate in _bundled_candidates(binary_name):
        if candidate.exists():
            return candidate
    return None


def find_ffmpeg():
    return _find_binary("ffmpeg")


def find_ffprobe():
    return _find_binary("ffprobe")


def check_ffmpeg():
    """Return ``(ffmpeg, ffprobe)`` path strings, or ``(None, None)``.

    Existence on disk is the gate — the same signal the Setup dialog
    uses, so boot and Setup can never disagree (that mismatch trapped
    users on the "Prerequisites Missing" landing while Setup insisted
    everything was installed).

    The ``-version`` call is a best-effort sanity probe only. A windowed
    PyInstaller build has flaky subprocess stdio, so a probe hiccup must
    NOT hide a working install — if the binaries are on disk we trust
    them and let the encode path surface any real ffmpeg error.
    """
    ffmpeg = find_ffmpeg()
    ffprobe = find_ffprobe()
    if not (ffmpeg and ffprobe):
        return None, None
    try:
        subprocess.run(
            [str(ffmpeg), "-version"],
            capture_output=True, timeout=8,
            stdin=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except Exception:
        pass  # trust the on-disk binary
    return str(ffmpeg), str(ffprobe)
