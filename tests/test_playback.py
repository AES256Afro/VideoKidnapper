# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Tests for the audio-mastered clock in core.playback.

Real playback needs hardware (speakers, ffmpeg runtime, native PortAudio)
so it's exercised manually / in integration. These tests pin the clock
math and the availability probe, which is enough to catch regressions
in the sync rule without opening an audio device.
"""
import time

from videokidnapper.core.playback import AudioClock, is_available


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
