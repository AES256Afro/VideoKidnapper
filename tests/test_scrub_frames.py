# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Scrubbing fetches preview frames without freezing the window."""

import sys
import threading
import time

import pytest

ctk = pytest.importorskip("customtkinter")
Image = pytest.importorskip("PIL.Image")


@pytest.fixture(scope="module")
def root():
    try:
        r = ctk.CTk()
    except Exception as exc:  # noqa: BLE001 - headless CI
        pytest.skip(f"no usable display: {type(exc).__name__}")
    # Mapped but invisible, like the other UI tests.
    r.attributes("-alpha", 0.0)
    if sys.platform == "win32":
        r.attributes("-toolwindow", True)
    r.geometry("800x450+-4000+-4000")
    yield r
    r.destroy()


@pytest.fixture
def player(root, monkeypatch):
    from videokidnapper.ui import video_player as vp

    fetched = []
    gate = threading.Event()
    gate.set()

    def slow_fetch(path, timestamp, **_kwargs):
        gate.wait(5)
        fetched.append((path, timestamp))
        time.sleep(0.05)   # an ffmpeg run
        return Image.new("RGB", (320, 180), (int(timestamp * 10) % 255, 0, 0))

    monkeypatch.setattr(vp, "get_frame_at", slow_fetch)
    monkeypatch.setattr(vp, "peek_frame", lambda *_a: None)
    p = vp.VideoPlayer(root)
    p.pack(fill="both", expand=True)
    root.update()
    p.video_path = "clip.mp4"
    p.duration = 10.0
    rendered = []
    real_render = p._render_frame
    p._render_frame = lambda frame, ts: (rendered.append(ts), real_render(frame, ts))
    p.fetched, p.rendered, p.gate = fetched, rendered, gate
    yield p
    p.destroy()


def _pump(root, until, timeout=5.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end and not until():
        root.update()
        time.sleep(0.005)
    return until()


def test_request_returns_at_once_and_the_frame_follows(root, player):
    started = time.perf_counter()
    player.request_frame(2.0)
    assert time.perf_counter() - started < 0.03, "the window waited for ffmpeg"
    assert _pump(root, lambda: player.rendered == [2.0])
    assert player.current_time == 2.0


def test_the_newest_position_wins(root, player):
    player.gate.clear()            # hold the worker on its first fetch
    for t in (1.0, 2.0, 3.0, 4.0):
        player.request_frame(t)
    player.gate.set()
    assert _pump(root, lambda: player.rendered and player.rendered[-1] == 4.0)
    # The positions dragged past while a fetch ran were never fetched.
    assert [t for _p, t in player.fetched] == [1.0, 4.0]


def test_a_cached_frame_shows_immediately(root, player, monkeypatch):
    from videokidnapper.ui import video_player as vp
    monkeypatch.setattr(vp, "peek_frame", lambda *_a: Image.new("RGB", (320, 180)))
    player.request_frame(5.0)
    assert player.rendered == [5.0]
    assert player.fetched == []


def test_frames_for_a_replaced_video_are_dropped(root, player):
    player.gate.clear()
    player.request_frame(1.0)
    player.video_path = "other.mp4"
    player.gate.set()
    _pump(root, lambda: not player._frame_worker_running and player._frame_poll_id is None)
    assert player.rendered == []
