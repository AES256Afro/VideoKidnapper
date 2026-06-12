# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Tests for download retry/resume and the yt-dlp self-update helpers."""

import sys
import threading
import types

import pytest

from videokidnapper.core import downloader
from videokidnapper.core.downloader import _is_transient_error, _retry_delay
from videokidnapper.utils import ytdlp_update
from videokidnapper.utils.ytdlp_update import (
    _version_tuple, is_outdated, looks_like_extractor_failure,
)


# ---------------------------------------------------------------------------
# Transient-error classification
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("msg", [
    "HTTPSConnectionPool: Read timed out",
    "Connection reset by peer",
    "HTTP Error 503: Service Unavailable",
    "HTTP Error 429: Too Many Requests",
    "[Errno 11001] getaddrinfo failed",
    "ssl.SSLEOFError: EOF occurred in violation of protocol",
    "IncompleteRead(512 bytes read)",
])
def test_transient_errors_detected(msg):
    assert _is_transient_error(msg)


@pytest.mark.parametrize("msg", [
    "This video is private",
    "Unsupported URL: https://example.com",
    "Sign in to confirm your age",
    "HTTP Error 404: Not Found",
    "Video unavailable",
    "",
    None,
])
def test_permanent_errors_not_retried(msg):
    assert not _is_transient_error(msg)


def test_retry_delay_schedule_capped():
    assert _retry_delay(1) == 2
    assert _retry_delay(2) == 4
    assert _retry_delay(3) == 8
    assert _retry_delay(10) == 8


# ---------------------------------------------------------------------------
# download_video retry loop (with a fake yt_dlp module)
# ---------------------------------------------------------------------------

class _FakeYDL:
    """Stand-in for yt_dlp.YoutubeDL driven by a scripted failure plan."""

    plan = []          # mutated per-test: list of exceptions / "ok"
    calls = []

    def __init__(self, opts):
        self.opts = opts

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def extract_info(self, url, download=True):
        step = _FakeYDL.plan.pop(0)
        _FakeYDL.calls.append(step)
        if step == "ok":
            return {
                "title": "Test Clip",
                "requested_downloads": [{"filepath": "/tmp/clip.mp4"}],
            }
        raise Exception(step)


@pytest.fixture
def fake_ytdlp(monkeypatch):
    module = types.ModuleType("yt_dlp")
    module.YoutubeDL = _FakeYDL
    monkeypatch.setitem(sys.modules, "yt_dlp", module)
    # No real sleeping in the backoff.
    monkeypatch.setattr(downloader, "_retry_delay", lambda attempt: 0)
    _FakeYDL.plan = []
    _FakeYDL.calls = []
    return module


def test_transient_failure_then_success_retries(fake_ytdlp):
    _FakeYDL.plan = ["Connection reset by peer", "ok"]
    result = downloader.download_video("https://youtu.be/x", max_attempts=3)
    assert result["error"] is None
    assert result["path"] == "/tmp/clip.mp4"
    assert len(_FakeYDL.calls) == 2


def test_permanent_failure_does_not_retry(fake_ytdlp):
    _FakeYDL.plan = ["This video is private", "ok"]
    result = downloader.download_video("https://youtu.be/x", max_attempts=3)
    assert result["error"]
    assert len(_FakeYDL.calls) == 1


def test_transient_failures_exhaust_attempts(fake_ytdlp):
    _FakeYDL.plan = ["timed out", "timed out", "timed out"]
    result = downloader.download_video("https://youtu.be/x", max_attempts=3)
    assert result["error"]
    assert "timed out" in result["error"]
    assert len(_FakeYDL.calls) == 3


def test_cancel_short_circuits(fake_ytdlp):
    _FakeYDL.plan = ["Download cancelled"]
    cancel = threading.Event()
    result = downloader.download_video(
        "https://youtu.be/x", cancel_event=cancel, max_attempts=3)
    assert result["error"] == "cancelled"
    assert len(_FakeYDL.calls) == 1


def test_continuedl_enabled_in_opts():
    opts, _platform = downloader._build_ydl_opts(
        "https://youtu.be/x", None, lambda d: None)
    assert opts["continuedl"] is True


# ---------------------------------------------------------------------------
# ytdlp_update helpers
# ---------------------------------------------------------------------------

def test_version_tuple_parses_date_versions():
    assert _version_tuple("2026.04.10") == (2026, 4, 10)
    assert _version_tuple("2026.04.10.123456") == (2026, 4, 10, 123456)


def test_version_tuple_tolerates_junk():
    assert _version_tuple(None) == (0,)
    assert _version_tuple("abc.def") == (0, 0)


def test_is_outdated():
    assert is_outdated("2025.12.01", "2026.04.10")
    assert not is_outdated("2026.04.10", "2026.04.10")
    assert not is_outdated("2026.05.01", "2026.04.10")
    assert not is_outdated(None, "2026.04.10")
    assert not is_outdated("2026.04.10", None)


@pytest.mark.parametrize("msg", [
    "ERROR: Unable to extract player version",
    "Unsupported URL: https://newplatform.example",
    "Requested format is not available",
    "HTTP Error 403: Forbidden",
    "nsig extraction failed: some detail",
])
def test_extractor_failure_signatures(msg):
    assert looks_like_extractor_failure(msg)


@pytest.mark.parametrize("msg", [
    "This video is private",
    "Connection reset by peer",
    "",
    None,
])
def test_non_extractor_failures(msg):
    assert not looks_like_extractor_failure(msg)


def test_update_refused_on_frozen_build(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    ok, msg = ytdlp_update.update_via_pip()
    assert not ok
    assert "release" in msg.lower()


def test_update_calls_pip(monkeypatch):
    monkeypatch.setattr(ytdlp_update, "is_frozen", lambda: False)
    calls = {}

    def fake_pip_install(package, user=True, upgrade=False, timeout=240):
        calls["package"] = package
        calls["upgrade"] = upgrade
        return True, "ok"

    import videokidnapper.utils.prereq_check as prereq_check
    monkeypatch.setattr(prereq_check, "pip_install", fake_pip_install)
    ok, msg = ytdlp_update.update_via_pip()
    assert ok
    assert calls == {"package": "yt-dlp", "upgrade": True}


def test_fetch_latest_version_swallows_network_errors(monkeypatch):
    import urllib.request

    def boom(*a, **k):
        raise OSError("no network")

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    assert ytdlp_update.fetch_latest_version() is None


# ---------------------------------------------------------------------------
# Cookie resolution + cookie-error friendliness
# ---------------------------------------------------------------------------

def test_resolve_cookies_none_when_unconfigured():
    assert downloader.resolve_cookies("", "") is None
    assert downloader.resolve_cookies() is None


def test_resolve_cookies_browser():
    assert downloader.resolve_cookies("firefox", "") == {"browser": "firefox"}


def test_resolve_cookies_file():
    assert (downloader.resolve_cookies("", "C:/c/cookies.txt")
            == {"file": "C:/c/cookies.txt"})


def test_resolve_cookies_file_wins_over_browser():
    # A hand-edited settings file may carry both; the file wins.
    assert (downloader.resolve_cookies("chrome", "/x/cookies.txt")
            == {"file": "/x/cookies.txt"})


@pytest.mark.parametrize("msg", [
    "ERROR: Could not copy Chrome cookie database. See https://github.com/yt-dlp...",
    "Failed to decrypt with DPAPI cookies from chrome",
    "could not find chrome cookies database in ...",
    "App-Bound encryption prevents reading Chrome cookies",
])
def test_cookie_errors_detected(msg):
    assert downloader._is_cookie_error(msg)


@pytest.mark.parametrize("msg", [
    "This video is private",
    "Could not copy file to temp dir",     # no 'cookie' in message
    "Sign in to confirm your age",
    "",
    None,
])
def test_non_cookie_errors_not_matched(msg):
    assert not downloader._is_cookie_error(msg)


def test_friendly_error_cookie_branch_is_actionable():
    raw = "ERROR: Could not copy Chrome cookie database. See https://..."
    out = downloader._friendly_error(raw, "YouTube")
    # Every escape route must be named, and the actions must appear
    # early enough to survive the status bar's 160-char truncation.
    head = out[:160]
    assert "Close the browser" in head
    assert "firefox" in head
    assert "Cookies file" in head
    assert "(raw:" in out


def test_friendly_error_cookie_branch_wins_over_login_hint():
    # Cookie-read failures often contain 'see https://...' text that can
    # also trip the login/private heuristics; the cookie branch must win.
    raw = "Could not copy Chrome cookie database; cookies not available"
    out = downloader._friendly_error(raw, "Instagram")
    assert "Browser cookies unreadable" in out
