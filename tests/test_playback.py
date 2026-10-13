# SPDX-FileCopyrightText: 2026 AES256Afro <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Tests for the audio-mastered clock in core.playback.

Real playback needs hardware (speakers, ffmpeg runtime, native PortAudio)
so it's exercised manually / in integration. These tests pin the clock
math and the availability probe, which is enough to catch regressions
in the sync rule without opening an audio device.
"""
import sys
import threading
import time
import types

import pytest

from videokidnapper.core import playback
from videokidnapper.core.playback import (
    AudioClock, AudioVideoPlayer, is_available,
)


def test_fresh_clock_returns_base_time():
    c = AudioClock(base_time=12.5, sample_rate=44100)
    c.reset(base_time=12.5)
    # Wall clock diff should be nearly zero at reset; allow a small slack.
    assert abs(c.time_now() - 12.5) < 0.05


def test_mark_advances_time_by_samples_over_rate():
    c = AudioClock(base_time=0.0, sample_rate=44100)
    c.reset(base_time=0.0)
    # Exactly 1 second of audio samples.
    c.mark(44100)
    # Sample-based clock takes over once we've marked anything. Because
    # time_now() returns base + samples/rate when samples>0, we should
    # be exactly at 1.0s regardless of wall-clock elapsed.
    assert abs(c.time_now() - 1.0) < 1e-9


def test_wall_clock_used_before_any_samples():
    c = AudioClock(base_time=0.0, sample_rate=44100)
    c.reset(base_time=0.0)
    # No samples yet — the wall-clock branch kicks in so video can
    # still advance for silent clips / first-ms-before-audio.
    time.sleep(0.05)
    t = c.time_now()
    assert 0.03 <= t <= 0.15, f"expected ~0.05s, got {t}"


def test_reset_rewinds():
    c = AudioClock(base_time=0.0, sample_rate=44100)
    c.reset(base_time=10.0)
    c.mark(44100)
    assert abs(c.time_now() - 11.0) < 1e-9
    c.reset(base_time=3.0)
    # After reset, sample count is zero → wall-clock branch.
    assert abs(c.time_now() - 3.0) < 0.05


def test_zero_sample_rate_falls_back_to_wall_clock_only():
    # sample_rate=None signals "no audio on this clip, use wall clock".
    c = AudioClock(base_time=5.0, sample_rate=None)
    c.reset(base_time=5.0)
    # Marks are tolerated but ignored — wall-clock still drives time.
    c.mark(99999)
    time.sleep(0.02)
    t = c.time_now()
    assert 5.0 <= t <= 5.10, f"expected ~5.0s via wall clock, got {t}"


def test_is_available_is_boolean():
    # Whether deps are installed depends on the env — just pin the shape.
    assert isinstance(is_available(), bool)


def test_stop_on_fresh_player_does_not_fire_finished():
    # Regression: play() calls stop() to tear down any prior session.
    # On a fresh player (nothing running) that must NOT spuriously fire
    # on_finished("stopped") — which would make the UI flip the play
    # button back to "Play" the instant playback starts.
    calls = []
    p = AudioVideoPlayer(
        "nonexistent.mp4",
        render_callback=lambda img, ts: None,
        on_finished=lambda reason: calls.append(reason),
    )
    p.stop()
    assert calls == []


def test_stop_while_running_fires_finished_once():
    # When something is actually playing, stop() reports "stopped" exactly
    # once.
    calls = []
    p = AudioVideoPlayer(
        "nonexistent.mp4",
        render_callback=lambda img, ts: None,
        on_finished=lambda reason: calls.append(reason),
    )
    p._running = True  # simulate an active session without opening a device
    p.stop()
    assert calls == ["stopped"]


def test_finished_clock_keeps_running_on_the_wall_clock():
    # When the sound runs out before the picture, time must keep going,
    # or the video thread waits forever for its next frame.
    c = AudioClock(base_time=0.0, sample_rate=44100)
    c.reset(base_time=0.0)
    c.mark(44100)
    c.finish()
    t1 = c.time_now()
    time.sleep(0.05)
    t2 = c.time_now()
    assert abs(t1 - 1.0) < 0.02
    assert 0.03 <= t2 - t1 <= 0.2


# ---------------------------------------------------------------------------
# The player's threads, with fakes for ffmpeg, the frame reader and the
# sound device. No audio device is opened and nothing is audible.
# ---------------------------------------------------------------------------

class _FakeStream:
    """Records every call and the thread that made it."""

    calls = []

    def __init__(self, **_kwargs):
        self._record("open")

    def _record(self, name):
        _FakeStream.calls.append((name, threading.current_thread().name))

    def start(self):
        self._record("start")

    def write(self, _data):
        self._record("write")
        time.sleep(0.004)

    def stop(self):
        self._record("stop")

    def abort(self):
        self._record("abort")

    def close(self):
        self._record("close")


class _FakeProc:
    """An ffmpeg PCM pipe: ``chunks`` reads of audio, then end of file."""

    def __init__(self, chunks):
        self._left = chunks
        self._killed = threading.Event()
        self.stdout = self

    def read(self, size):
        if self._killed.is_set() or self._left == 0:
            return b""
        if self._left > 0:
            self._left -= 1
        return b"\0" * size

    def terminate(self):
        self._killed.set()


def _fake_reader(frames, fps):
    def read_frames(*_a, **_k):
        yield {"size": (4, 2), "fps": fps}
        for _ in range(frames):
            yield b"\0" * (4 * 2 * 3)
    return read_frames


@pytest.fixture
def fake_av(monkeypatch):
    """Install the fakes; returns a setter for the clip's shape."""
    pytest.importorskip("numpy")
    pytest.importorskip("PIL")
    _FakeStream.calls = []
    monkeypatch.setitem(sys.modules, "sounddevice",
                        types.SimpleNamespace(OutputStream=_FakeStream))
    shape = {"audio_chunks": -1, "frames": 10_000, "fps": 100.0}
    monkeypatch.setitem(sys.modules, "imageio_ffmpeg", types.SimpleNamespace(
        read_frames=lambda *a, **k: _fake_reader(shape["frames"], shape["fps"])(*a, **k)))
    monkeypatch.setattr(playback.subprocess, "Popen",
                        lambda *a, **k: _FakeProc(shape["audio_chunks"]))
    monkeypatch.setattr(
        "videokidnapper.core.ffmpeg.probe.preview_color_filter", lambda _p: None)
    return shape


def _player(events):
    return AudioVideoPlayer(
        "clip.mp4",
        render_callback=lambda img, ts: events.append(("frame", ts)),
        on_finished=lambda reason: events.append(("finished", reason)),
    )


def _wait_for(predicate, timeout=5.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def test_stop_leaves_the_stream_to_the_audio_thread(fake_av):
    """Pausing crashed the app: stop() stopped and closed the sound stream
    from the Tk thread while the audio thread was closing it too."""
    events = []
    p = _player(events)
    p.play(0.0)
    assert _wait_for(lambda: ("write", "AudioVideoPlayer-audio") in _FakeStream.calls)
    # Generous wait: a loaded CI machine can take a while to schedule it.
    p.stop(wait=10.0)
    assert not p._audio_thread.is_alive()
    callers = {thread for _name, thread in _FakeStream.calls}
    assert callers == {"AudioVideoPlayer-audio"}, _FakeStream.calls
    names = [name for name, _thread in _FakeStream.calls]
    # A stop cuts the sound at once (abort), and the stream closes once.
    assert names.count("close") == 1 and "abort" in names
    assert events[-1] == ("finished", "stopped")


def test_a_clip_without_sound_plays_to_the_last_frame(fake_av):
    """A silent file (screen recording, GIF) has no audio to read. The
    audio thread used to call that the end of the clip at once, so
    playback stopped a quarter of a second in."""
    fake_av.update(audio_chunks=0, frames=20)
    events = []
    p = _player(events)
    p.play(0.0)
    assert _wait_for(lambda: ("finished", "end") in events)
    frames = [e for e in events if e[0] == "frame"]
    assert len(frames) == 20
    assert events.index(("finished", "end")) == len(events) - 1
    # It never needed the sound device.
    assert _FakeStream.calls == []


def test_picture_longer_than_sound_still_reaches_the_end(fake_av):
    """Once the audio runs out the clock carries on, so the remaining
    frames play and the clip ends."""
    fake_av.update(audio_chunks=2, frames=30)   # ~46 ms of sound, 0.3 s of video
    events = []
    p = _player(events)
    p.play(0.0)
    assert _wait_for(lambda: ("finished", "end") in events)
    assert len([e for e in events if e[0] == "frame"]) == 30
    names = [name for name, _thread in _FakeStream.calls]
    # A natural end lets the queued sound play out (stop, not abort).
    assert "stop" in names and "abort" not in names and names[-1] == "close"
