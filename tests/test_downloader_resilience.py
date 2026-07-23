# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Tests for download retry/resume and the yt-dlp self-update helpers."""

import io
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
    # Keep the network preflight out of the way (and off the wire) unless a
    # test overrides it — these exercise the retry loop, not connectivity.
    monkeypatch.setattr(downloader, "has_internet", lambda *a, **k: True)
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
# Offline handling (Store policy 10.1.2.10: graceful when offline)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("msg", [
    "ERROR: Unable to download webpage: <urlopen error [Errno 11001] getaddrinfo failed>",
    "Failed to resolve 'www.youtube.com'",
    "Temporary failure in name resolution",
    "[Errno 101] Network is unreachable",
])
def test_offline_errors_detected(msg):
    assert downloader._is_offline_error(msg)


@pytest.mark.parametrize("msg", [
    "This video is private",
    "HTTP Error 403: Forbidden",
    "",
    None,
])
def test_non_offline_errors_not_matched(msg):
    assert not downloader._is_offline_error(msg)


def test_offline_dns_failure_fails_fast_with_clear_message(fake_ytdlp, monkeypatch):
    # Fully offline: yt-dlp fails once with a DNS error, has_internet()
    # confirms the connection is down — no retry storm, plain message.
    monkeypatch.setattr(downloader, "has_internet", lambda *a, **k: False)
    _FakeYDL.plan = ["<urlopen error [Errno 11001] getaddrinfo failed>", "ok"]

    result = downloader.download_video("https://youtu.be/x", max_attempts=3)

    assert result["error"] == downloader.OFFLINE_MESSAGE
    assert "internet" in result["error"].lower()
    assert len(_FakeYDL.calls) == 1          # did NOT retry the offline error


def test_dns_failure_while_online_reports_bad_link_not_offline(fake_ytdlp, monkeypatch):
    # Online, but this one host won't resolve (typo'd/dead domain): a
    # different message, and still no retry.
    monkeypatch.setattr(downloader, "has_internet", lambda *a, **k: True)
    _FakeYDL.plan = ["Failed to resolve 'notarealsite.example'", "ok"]

    result = downloader.download_video("https://notarealsite.example/x", max_attempts=3)

    assert result["error"] != downloader.OFFLINE_MESSAGE
    assert "reach that link" in result["error"].lower()
    assert len(_FakeYDL.calls) == 1


def test_online_download_still_succeeds(fake_ytdlp):
    _FakeYDL.plan = ["ok"]
    result = downloader.download_video("https://youtu.be/x", max_attempts=3)
    assert result["error"] is None
    assert result["path"] == "/tmp/clip.mp4"


def test_probe_offline_error_maps_to_friendly_message():
    assert (downloader._friendly_error("getaddrinfo failed", "Instagram")
            == downloader.OFFLINE_MESSAGE)


# ---------------------------------------------------------------------------
# Reddit image/GIF fallback (yt-dlp can't extract the /media redirect)
# ---------------------------------------------------------------------------

_REDDIT_MEDIA_ERR = (
    "ERROR: Unsupported URL: https://www.reddit.com/media"
    "?url=https%3A%2F%2Fi.redd.it%2Fq85z6hwpk3ch1.gif"
)


def test_reddit_media_url_decodes_the_embedded_target():
    assert (downloader._reddit_media_url(_REDDIT_MEDIA_ERR)
            == "https://i.redd.it/q85z6hwpk3ch1.gif")


@pytest.mark.parametrize("msg", [
    "This video is private",
    "Unsupported URL: https://newplatform.example",
    "",
    None,
])
def test_reddit_media_url_none_for_other_errors(msg):
    assert downloader._reddit_media_url(msg) is None


def test_reddit_gif_fallback_downloads_without_retrying(fake_ytdlp, monkeypatch):
    _FakeYDL.plan = [_REDDIT_MEDIA_ERR]  # a single yt-dlp failure, no "ok"

    captured = {}

    def fake_direct(media_url, progress_callback=None, cancel_event=None):
        captured["url"] = media_url
        return "/tmp/q85z6hwpk3ch1.gif"

    monkeypatch.setattr(downloader, "_download_direct_media", fake_direct)
    result = downloader.download_video(
        "https://www.reddit.com/r/x/comments/1uraihz/foo/", max_attempts=3)

    assert result["error"] is None
    assert result["path"] == "/tmp/q85z6hwpk3ch1.gif"
    assert result["title"] == "q85z6hwpk3ch1"
    assert captured["url"] == "https://i.redd.it/q85z6hwpk3ch1.gif"
    assert len(_FakeYDL.calls) == 1     # fell through to direct fetch, not retried


def test_reddit_media_fallback_reports_still_image(fake_ytdlp, monkeypatch):
    _FakeYDL.plan = [_REDDIT_MEDIA_ERR]

    def fake_direct(media_url, progress_callback=None, cancel_event=None):
        raise RuntimeError("this Reddit post is not a video or GIF (got image/jpeg)")

    monkeypatch.setattr(downloader, "_download_direct_media", fake_direct)
    result = downloader.download_video(
        "https://www.reddit.com/r/x/comments/abc/foo/", max_attempts=3)

    assert result["path"] is None
    assert "not a video or GIF" in result["error"]
    assert len(_FakeYDL.calls) == 1


def test_reddit_media_fallback_honours_cancel(fake_ytdlp, monkeypatch):
    _FakeYDL.plan = [_REDDIT_MEDIA_ERR]

    def fake_direct(media_url, progress_callback=None, cancel_event=None):
        raise Exception("Download cancelled")

    monkeypatch.setattr(downloader, "_download_direct_media", fake_direct)
    result = downloader.download_video(
        "https://www.reddit.com/r/x/comments/abc/foo/", max_attempts=3)

    assert result["error"] == "cancelled"


# ---------------------------------------------------------------------------
# Native direct-media provider
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("url", [
    "https://cdn.example/clip.mp4",
    "https://cdn.example/CLIP.WEBM?token=abc",
    "https://cdn.example/animation.gif#preview",
])
def test_native_provider_accepts_supported_direct_media(url):
    assert downloader.NativeDirectProvider().can_handle(url)


@pytest.mark.parametrize("url", [
    "https://example.com/watch/123",
    "https://example.com/master.m3u8",
    "file:///tmp/clip.mp4",
    "",
])
def test_native_provider_leaves_pages_and_manifests_to_compatibility(url):
    assert not downloader.NativeDirectProvider().can_handle(url)


def test_direct_url_uses_native_provider_before_ytdlp(fake_ytdlp, monkeypatch):
    monkeypatch.setattr(
        downloader, "_download_direct_media",
        lambda *args, **kwargs: "/tmp/native_clip.mp4",
    )

    result = downloader.download_video("https://cdn.example/native_clip.mp4")

    assert result["error"] is None
    assert result["path"] == "/tmp/native_clip.mp4"
    assert result["provider"] == "VideoKidnapper native"
    assert _FakeYDL.calls == []


def test_native_failure_falls_back_to_ytdlp(fake_ytdlp, monkeypatch):
    def fail_native(*args, **kwargs):
        raise RuntimeError("server rejected direct request")

    monkeypatch.setattr(downloader, "_download_direct_media", fail_native)
    _FakeYDL.plan = ["ok"]

    result = downloader.download_video("https://cdn.example/clip.mp4")

    assert result["error"] is None
    assert result["path"] == "/tmp/clip.mp4"
    assert result["provider"] == "yt-dlp compatibility"
    assert len(_FakeYDL.calls) == 1


class _DirectResponse:
    def __init__(self, body, content_type="video/mp4", url="https://cdn/x.mp4"):
        self._body = io.BytesIO(body)
        self.headers = {
            "Content-Type": content_type,
            "Content-Length": str(len(body)),
        }
        self._url = url

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self, size=-1):
        return self._body.read(size)

    def geturl(self):
        return self._url


def test_direct_download_writes_complete_file_atomically(tmp_path, monkeypatch):
    import urllib.request

    payload = b"not-real-video-but-nonempty"
    monkeypatch.setattr(downloader, "TEMP_DIR", tmp_path)
    monkeypatch.setattr(
        urllib.request, "urlopen",
        lambda *args, **kwargs: _DirectResponse(payload),
    )

    path = downloader._download_direct_media("https://cdn.example/x.mp4")

    assert path == str(tmp_path / "x.mp4")
    assert (tmp_path / "x.mp4").read_bytes() == payload
    assert list(tmp_path.glob("*.part")) == []


def test_direct_download_cancel_removes_partial_file(tmp_path, monkeypatch):
    import urllib.request

    cancel = threading.Event()
    cancel.set()
    monkeypatch.setattr(downloader, "TEMP_DIR", tmp_path)
    monkeypatch.setattr(
        urllib.request, "urlopen",
        lambda *args, **kwargs: _DirectResponse(b"partial-video"),
    )

    with pytest.raises(Exception, match="cancelled"):
        downloader._download_direct_media(
            "https://cdn.example/x.mp4", cancel_event=cancel,
        )

    assert list(tmp_path.iterdir()) == []


def test_direct_download_rejects_html(tmp_path, monkeypatch):
    import urllib.request

    monkeypatch.setattr(downloader, "TEMP_DIR", tmp_path)
    monkeypatch.setattr(
        urllib.request, "urlopen",
        lambda *args, **kwargs: _DirectResponse(
            b"<html>not media</html>", content_type="text/html",
        ),
    )

    with pytest.raises(RuntimeError, match="video or GIF"):
        downloader._download_direct_media("https://cdn.example/fake.mp4")

    assert list(tmp_path.iterdir()) == []


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
