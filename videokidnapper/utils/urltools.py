# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Tiny pure helpers for deciding what pasted clipboard text *is*.

Used by the app-level Ctrl+V router: a single http(s)/www link switches
to the Kidnap downloader tab; anything else falls through to the active
tab's own paste behaviour (e.g. clipboard-image overlay on Trim).
"""


def looks_like_media_url(text):
    """True when ``text`` is a single web link (one token, http/https/www).

    Deliberately conservative: multi-line clipboards, sentences that
    happen to contain a URL, and file paths all return False so we never
    hijack a paste the user meant for something else.
    """
    if not text:
        return False
    t = text.strip()
    if not t or any(ch.isspace() for ch in t):
        return False
    low = t.lower()
    return low.startswith(("http://", "https://", "www."))
