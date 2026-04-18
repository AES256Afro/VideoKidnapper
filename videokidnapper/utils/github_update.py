"""Minimal 'check GitHub releases for a newer version' helper.

Runs on a daemon thread with a short timeout; never blocks UI, never raises
into the caller. Returns `(latest_tag, html_url)` or `None` on any error.
"""

import json
import re
import threading
import urllib.request


GITHUB_REPO = "AES256Afro/VideoKidnapper"
_TIMEOUT_S = 4


def _normalize(version):
    """Turn 'v1.2.3' or '1.2.3-beta' into a comparable tuple of ints."""
    m = re.match(r"v?(\d+)\.(\d+)(?:\.(\d+))?", str(version))
    if not m:
        return (0, 0, 0)
    return tuple(int(x) if x else 0 for x in m.groups())


def is_newer(latest, current):
    return _normalize(latest) > _normalize(current)


def fetch_latest(repo=GITHUB_REPO):
    """Synchronous fetch. Returns ``(tag_name, html_url)`` or ``None``."""
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    try:
        req = urllib.request.Request(
            url, headers={"Accept": "application/vnd.github+json"},
        )
        with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as resp:
            data = json.load(resp)
        tag = data.get("tag_name")
        link = data.get("html_url")
        if tag and link:
            return (tag, link)
    except Exception:
        return None
    return None


def check_async(current_version, on_update_available, repo=GITHUB_REPO):
    """Run ``fetch_latest`` in a thread; call callback only when newer.

    ``on_update_available(latest_tag, html_url)`` runs on the background
    thread — callers must marshal back to the UI thread themselves.
    """

    def worker():
        result = fetch_latest(repo)
        if not result:
            return
        tag, link = result
        if is_newer(tag, current_version):
            try:
                on_update_available(tag, link)
            except Exception:
                pass

    threading.Thread(target=worker, daemon=True).start()
