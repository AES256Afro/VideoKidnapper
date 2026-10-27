# SPDX-FileCopyrightText: 2026 AES256Afro <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""A failed export says why, in words, instead of "Clip 1 failed"."""

import threading

import pytest

from videokidnapper.core.ffmpeg_backend import (
    _log_ffmpeg_failure, explain_ffmpeg_failure, take_failure_advice,
)


@pytest.mark.parametrize("tail, words", [
    ("out.mp4: No space left on device", "drive is full"),
    ("D:/clips/out.mp4: Permission denied", "another Save to folder"),
    ("clip.mp4: No such file or directory", "has gone"),
    ("moov atom not found\nclip.mp4: Invalid data found when processing input",
     "damaged"),
    ("[h264_nvenc @ 0x1] OpenEncodeSessionEx failed: out of memory", "memory"),
    ("[h264_nvenc @ 0x1] No capable devices found", "hardware encoding"),
    ("width not divisible by 2 (1081x720)", "odd"),
    ("something nobody has seen before", "Debug log"),
])
def test_common_failures_get_plain_advice(tail, words):
    assert words in explain_ffmpeg_failure(tail)


def test_the_reason_is_kept_for_the_thread_that_failed_once():
    _log_ffmpeg_failure(["ffmpeg", "-i", "x", "out.mp4"], 1, "No space left on device")
    seen_elsewhere = []
    worker = threading.Thread(target=lambda: seen_elsewhere.append(take_failure_advice()))
    worker.start()
    worker.join()
    assert seen_elsewhere == [None]
    assert "drive is full" in take_failure_advice()
    assert take_failure_advice() is None
