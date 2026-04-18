# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Tests for the Tier 1 robustness fixes.

- ``get_video_info`` raises ProbeError on bad files / missing ffprobe /
  non-JSON output (used to land as an uncaught JSONDecodeError).
- ``get_video_info_from_url`` returns an error dict on timeout instead
  of hanging forever on a stalled URL.
- Settings file is written atomically via tempfile + os.replace, and
  ``add_history_entry`` is thread-safe across concurrent callers.
"""
import json
import threading
from unittest.mock import MagicMock, patch

import pytest

from videokidnapper.core.ffmpeg_backend import ProbeError, get_video_info


# ---------------------------------------------------------------------------
# ffprobe error funnel
# ---------------------------------------------------------------------------

def test_get_video_info_raises_on_non_json_output():
    fake = MagicMock(returncode=0, stdout="not json", stderr="")
    with patch("videokidnapper.core.ffmpeg_backend.subprocess.run",
               return_value=fake):
        with pytest.raises(ProbeError, match="non-JSON"):
            get_video_info("bogus.mp4")


def test_get_video_info_raises_on_nonzero_exit():
    fake = MagicMock(
        returncode=1, stdout="",
        stderr="bogus.mp4: Invalid data found when processing input\n",
    )
    with patch("videokidnapper.core.ffmpeg_backend.subprocess.run",
               return_value=fake):
        with pytest.raises(ProbeError, match="ffprobe exited 1"):
            get_video_info("bogus.mp4")


def test_get_video_info_raises_on_ffprobe_missing():
    with patch(
        "videokidnapper.core.ffmpeg_backend.subprocess.run",
        side_effect=FileNotFoundError("no such file"),
    ):
        with pytest.raises(ProbeError, match="not found"):
            get_video_info("bogus.mp4")


def test_get_video_info_raises_on_timeout():
    import subprocess as sp
    with patch(
        "videokidnapper.core.ffmpeg_backend.subprocess.run",
        side_effect=sp.TimeoutExpired(cmd="ffprobe", timeout=10),
    ):
        with pytest.raises(ProbeError, match="timed out"):
            get_video_info("bogus.mp4")


def test_get_video_info_succeeds_on_well_formed_output():
    payload = json.dumps({
        "format": {"duration": "12.5"},
        "streams": [
            {"codec_type": "video", "width": 640, "height": 360,
             "r_frame_rate": "30/1"},
        ],
    })
    fake = MagicMock(returncode=0, stdout=payload, stderr="")
    with patch("videokidnapper.core.ffmpeg_backend.subprocess.run",
               return_value=fake):
        info = get_video_info("ok.mp4")
    assert info["duration"] == 12.5
    assert info["width"] == 640
    assert info["height"] == 360


# ---------------------------------------------------------------------------
# yt-dlp probe timeout
# ---------------------------------------------------------------------------

def test_get_video_info_from_url_times_out_cleanly():
    """Stalled ``extract_info`` should yield an error dict, not a hang."""
    import time

    from videokidnapper.core import downloader

    class StalledYdl:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def extract_info(self, *a, **k):
            time.sleep(10)  # would hang caller without the soft timeout
            return {}

    with patch.object(downloader, "__import__", create=True):
        pass  # placeholder so the import patching below is self-contained

    with patch("yt_dlp.YoutubeDL", StalledYdl, create=True):
        out = downloader.get_video_info_from_url("http://example.com", timeout=1)
    assert "error" in out
    assert "timed out" in out["error"]


# ---------------------------------------------------------------------------
# Settings atomic write + concurrent history
# ---------------------------------------------------------------------------

@pytest.fixture
def fresh_settings(tmp_path, monkeypatch):
    from videokidnapper.utils import settings
    monkeypatch.setattr(settings, "_SETTINGS_PATH", tmp_path / "s.json")
    return settings


def test_set_produces_atomic_rename_no_leftover_tmp(fresh_settings, tmp_path):
    fresh_settings.set("quality", "High")
    # Only the canonical settings file exists — no leftover .tmp files.
    entries = [p.name for p in tmp_path.iterdir()]
    assert entries == ["s.json"], entries
    assert fresh_settings.get("quality") == "High"


def test_concurrent_history_entries_all_persisted(fresh_settings):
    """Two threads adding history simultaneously must both survive.

    Before the lock was added, each thread did read-modify-write with
    no coordination, and whichever wrote last clobbered the other's
    entry. We count the persisted entries to pin the fix.
    """
    N = 20
    errors = []

    def writer(idx):
        try:
            fresh_settings.add_history_entry({
                "path": f"/tmp/{idx}.mp4",
                "mode": "test",
                "size_bytes": idx,
            })
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=writer, args=(i,)) for i in range(N)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, errors
    history = fresh_settings.get_history()
    # All N writes landed (cap is 25, well above 20).
    assert len(history) == N
    paths = sorted(e["path"] for e in history)
    assert paths == sorted(f"/tmp/{i}.mp4" for i in range(N))
