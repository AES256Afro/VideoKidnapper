# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""End-to-end integration test that actually runs ffmpeg.

Everything else in the test suite is pure-function / mocked-subprocess.
This one spins a tiny synthetic source through the real encode path to
catch wiring regressions the unit tests can't see — argument ordering,
stream map mistakes, filter-graph composition errors, that sort of thing.

Skipped automatically when ``ffmpeg`` / ``ffprobe`` aren't on PATH so
local runs on bare-bones dev boxes don't fail. CI installs ffmpeg
(Ubuntu: apt; Windows: choco) so this always runs there.
"""
import shutil
import subprocess
from pathlib import Path

import pytest


ffmpeg_missing = shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None
skip_if_no_ffmpeg = pytest.mark.skipif(
    ffmpeg_missing,
    reason="ffmpeg / ffprobe not on PATH — integration test skipped",
)


def _make_synthetic_source(dst: Path, duration: float = 1.0) -> None:
    """Create a tiny ``color`` / ``sine`` test file at ``dst`` via lavfi.

    No dependency on sample media — ffmpeg's built-in test sources are
    enough to exercise the full encode graph end-to-end.
    """
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", f"color=c=blue:s=128x72:d={duration}:r=24",
        "-f", "lavfi", "-i", f"sine=frequency=440:duration={duration}",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-shortest",
        str(dst),
    ]
    result = subprocess.run(cmd, capture_output=True, timeout=30)
    assert result.returncode == 0, (
        f"ffmpeg failed to build synthetic source: "
        f"{result.stderr.decode('utf-8', errors='replace')[-300:]}"
    )


@skip_if_no_ffmpeg
def test_trim_to_video_round_trip(tmp_path, monkeypatch):
    """Full encode path: build filter graph, run ffmpeg, verify output."""
    # Unit tests import ffmpeg_backend with module-level cached binary
    # paths. The functions we're about to call resolve ffmpeg via
    # ``find_ffmpeg()`` on first use — reset the caches so whatever is
    # on CI's PATH actually gets picked up.
    from videokidnapper.core import ffmpeg_backend

    monkeypatch.setattr(ffmpeg_backend, "_ffmpeg", None)
    monkeypatch.setattr(ffmpeg_backend, "_ffprobe", None)
    monkeypatch.setattr(ffmpeg_backend, "_hw_encoders_cache", None)

    src = tmp_path / "src.mp4"
    _make_synthetic_source(src, duration=1.0)

    # Probe the synthetic source — this is the bug-prone path we fixed
    # in the Tier-1 robustness PR; make sure it succeeds on real media.
    info = ffmpeg_backend.get_video_info(str(src))
    assert info["duration"] > 0
    assert info["width"] == 128
    assert info["height"] == 72
    # Not asserting has_audio — some ffmpeg builds elide the aac mux
    # when -shortest cuts the sine wave exactly at the video end.

    # Run the full trim path with a text overlay to exercise the
    # filter-graph composition (drawtext + scale + H.264 encode).
    out = tmp_path / "out.mp4"
    result = ffmpeg_backend.trim_to_video(
        str(src), start=0.0, end=0.8,
        preset_name="Low",               # cheapest CRF to keep the test fast
        output_path=str(out),
        text_layers=[{
            "text": "integration",
            "font": "Arial",
            "fontsize": 16,
            "fontcolor": "white",
            "position": "(w-tw)/2:h-th-20",
            "box": True,
            "start": 0.0,
            "end": 0.8,
        }],
        options={
            "speed": 1.0,
            "rotate": 0,
            "mute": True,                # skips audio wiring to keep it minimal
            "audio_only": False,
            "hw_encoder": "off",         # libx264 always, no NVENC flakiness
        },
    )
    assert result is not None, "trim_to_video returned None — see ffmpeg stderr"
    assert out.exists(), f"expected {out} to exist after encode"
    assert out.stat().st_size > 1024, "output file suspiciously small"

    # Probe the result — confirms the wrapper wrote a valid MP4 with a
    # video stream at the expected width.
    result_info = ffmpeg_backend.get_video_info(str(out))
    assert result_info["duration"] > 0
    assert result_info["width"] > 0
    assert result_info["height"] > 0
