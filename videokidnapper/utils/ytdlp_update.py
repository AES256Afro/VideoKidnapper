# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""yt-dlp staleness detection and one-click self-update.

yt-dlp breaks whenever a platform changes its player or signature scheme,
so a stale copy is the single most common real-world failure of the URL
tab. This module gives the UI three things:

- ``installed_version()`` / ``fetch_latest_version()`` — what we have vs.
  what PyPI has (yt-dlp uses date-based versions like ``2026.04.10``).
- ``update_via_pip()`` — upgrade in place via the same pip plumbing the
  Setup dialog uses. Frozen (PyInstaller) builds can't pip-install into
  themselves, so they get a clear message pointing at a new app release
  instead.
- ``looks_like_extractor_failure(msg)`` — heuristic for "this error
  smells like an outdated extractor", used to append an update hint to
  download-failure toasts.

Network calls take a short timeout and never raise; callers always get
``None`` / a ``(False, message)`` tuple on any failure.
"""

import json
import sys
import urllib.request


PYPI_JSON_URL = "https://pypi.org/pypi/yt-dlp/json"
_TIMEOUT_S = 6

# Error-text fragments that usually mean the extractor code is stale,
# not that the video is genuinely unavailable. Lowercase substrings.
_EXTRACTOR_FAILURE_SIGNS = (
    "unable to extract",
    "unsupported url",
    "requested format is not available",
    "sign in to confirm",
    "nsig extraction failed",
    "player response",
    "http error 403",
)


def installed_version():
    """Return the installed yt-dlp version string, or ``None``."""
    try:
        from yt_dlp.version import __version__
        return __version__
    except Exception:
        return None


def is_frozen():
    """True when running from a PyInstaller bundle (no pip available)."""
    return bool(getattr(sys, "frozen", False))


def fetch_latest_version(timeout=_TIMEOUT_S):
    """Return the newest yt-dlp version on PyPI, or ``None`` on any error."""
    try:
        with urllib.request.urlopen(PYPI_JSON_URL, timeout=timeout) as resp:
            data = json.load(resp)
        version = (data.get("info") or {}).get("version")
        return str(version) if version else None
    except Exception:
        return None


def _version_tuple(version):
    """``"2026.04.10"`` → ``(2026, 4, 10)``; junk segments become 0."""
    parts = []
    for piece in str(version or "").split(".")[:4]:
        try:
            parts.append(int(piece))
        except ValueError:
            parts.append(0)
    return tuple(parts) or (0,)


def is_outdated(current, latest):
    """True when ``latest`` is strictly newer than ``current``."""
    if not current or not latest:
        return False
    return _version_tuple(latest) > _version_tuple(current)


def looks_like_extractor_failure(msg):
    """Heuristic: does this download error smell like a stale yt-dlp?"""
    low = str(msg or "").lower()
    return any(sign in low for sign in _EXTRACTOR_FAILURE_SIGNS)


def update_via_pip():
    """Upgrade yt-dlp in place. Returns ``(ok, message)``.

    Frozen builds get a refusal with a pointer to the app's releases
    page — pip can't install into a PyInstaller bundle. On success the
    message says whether a restart is needed (it is whenever yt_dlp was
    already imported this session; the loaded module keeps running the
    old code).
    """
    if is_frozen():
        return False, (
            "This is a bundled build — yt-dlp updates ship with new "
            "VideoKidnapper releases. Check Help → GitHub releases."
        )
    from videokidnapper.utils.prereq_check import pip_install

    before = installed_version()
    ok, msg = pip_install("yt-dlp", upgrade=True)
    if not ok:
        return False, msg
    already_loaded = "yt_dlp" in sys.modules
    suffix = " Restart the app to use it." if already_loaded else ""
    if before:
        return True, f"yt-dlp upgraded (was {before}).{suffix}"
    return True, f"yt-dlp installed.{suffix}"
