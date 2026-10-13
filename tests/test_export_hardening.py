# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Export-pipeline fixes from the bug sweep that need no ffmpeg run."""

import subprocess
from types import SimpleNamespace

import pytest

from videokidnapper.core.ffmpeg import _internals, probe
from videokidnapper.core.ffmpeg.filters import (
    _build_drawtext_filter, _build_even_size, _build_final_scale, coerce_speed,
)
from videokidnapper.core.ffmpeg.encode import _output_duration, _ts
from videokidnapper.utils.ffmpeg_escape import escape_drawtext_value


# -- captions are literal text ----------------------------------------------

def test_percent_is_plain_text():
    assert escape_drawtext_value("100% done") == "100% done"
    spec = _build_drawtext_filter({"text": "100% %{pts}"})
    assert ":expansion=none:" in spec
    assert "text='100% %{pts}'" in spec


# -- speed and length ---------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    (2, 2.0), ("0.5", 0.5), (None, 1.0), ("fast", 1.0), (0, 1.0),
    (-3, 1.0), (float("nan"), 1.0), (float("inf"), 1.0), (0.01, 0.1), (500, 100.0),
])
def test_coerce_speed(raw, expected):
    assert coerce_speed(raw) == expected


def test_output_duration_is_the_sped_up_length():
    assert _output_duration(10.0, 20.0, 2.0) == 5.0
    assert _output_duration(10.0, 20.0, 0.5) == 20.0
    assert _output_duration(5.0, 5.0, 1.0) == 0.001


def test_times_never_use_exponent_notation():
    assert _ts(1e-05) == "0.000010"
    assert "e" not in _ts(12.5)


# -- frame size ----------------------------------------------------------------

_INFO = {"width": 1920, "height": 1080}


def test_manual_crop_overrides_the_aspect_box():
    options = {"crop": {"x": 0, "y": 0, "w": 800, "h": 800}, "aspect_preset": "9:16"}
    # Width-only: the 1:1 crop stays 1:1 instead of being forced to 9:16.
    assert _build_final_scale("Medium", _INFO, options) == "scale=720:-2"


def test_aspect_box_without_a_manual_crop():
    assert _build_final_scale("Medium", _INFO, {"aspect_preset": "9:16"}) == "scale=720:1280"


def test_even_size_only_for_odd_frames_with_no_scale():
    odd = {"crop": {"x": 0, "y": 0, "w": 301, "h": 201}}
    assert _build_even_size("Ultra", _INFO, odd) == "crop=trunc(iw/2)*2:trunc(ih/2)*2"
    assert _build_even_size("Ultra", _INFO, {"crop": {"x": 0, "y": 0, "w": 300, "h": 200}}) is None
    assert _build_even_size("Low", _INFO, {}) is None       # the scale evens it


def test_even_size_when_crop_is_narrower_than_the_preset():
    odd = {"crop": {"x": 0, "y": 0, "w": 301, "h": 201}}
    # Medium is 720 wide; a 301-wide crop is not scaled, so it must be evened.
    assert _build_final_scale("Medium", _INFO, odd) is None
    assert _build_even_size("Medium", _INFO, odd) is not None


# -- probing odd ffprobe output -------------------------------------------------

def _fake_probe(monkeypatch, stdout):
    def run(cmd, **kwargs):
        return SimpleNamespace(returncode=0, stdout=stdout, stderr="")
    monkeypatch.setattr(probe.subprocess, "run", run)
    monkeypatch.setattr(probe, "_get_ffprobe", lambda: "ffprobe")


@pytest.mark.parametrize("stdout", ["[]", "null", '"text"', "3"])
def test_probe_rejects_json_that_is_not_an_object(monkeypatch, stdout):
    _fake_probe(monkeypatch, stdout)
    with pytest.raises(probe.ProbeError):
        probe.get_video_info("x.mp4")


def test_probe_tolerates_missing_and_garbage_fields(monkeypatch):
    _fake_probe(monkeypatch, '{"streams": [null, {"codec_type": "video", "width": null,'
                             ' "height": "tall", "r_frame_rate": 30}],'
                             ' "format": {"duration": "N/A"}}')
    info = probe.get_video_info("x.mp4")
    assert (info["width"], info["height"], info["duration"]) == (0, 0, 0.0)
    assert info["fps"] == 30.0 and info["has_video"] and not info["has_audio"]


def test_probe_that_cannot_start_is_a_probe_error(monkeypatch):
    def run(cmd, **kwargs):
        raise PermissionError(13, "Access is denied")
    monkeypatch.setattr(probe.subprocess, "run", run)
    monkeypatch.setattr(probe, "_get_ffprobe", lambda: "ffprobe")
    with pytest.raises(probe.ProbeError, match="could not run"):
        probe.get_video_info("x.mp4")


# -- progress parsing ---------------------------------------------------------

class _Process:
    def __init__(self, lines):
        self.stderr = SimpleNamespace(readline=iter(lines + [""]).__next__)
        self.killed = False

    def kill(self):
        self.killed = True

    def poll(self):
        return None


def test_failing_progress_callback_stops_ffmpeg():
    process = _Process(["frame=1 time=00:00:01.00 bitrate=1"])

    def callback(p):
        raise RuntimeError("dialog is gone")

    with pytest.raises(RuntimeError):
        _internals._parse_progress(process, 10.0, callback, None)
    assert process.killed


def test_subprocess_text_is_read_as_utf8():
    # ffmpeg writes UTF-8; Windows' default (cp1252) turned a non-ASCII
    # path in an error message into an exception on the progress thread.
    import re
    from pathlib import Path
    import videokidnapper
    root = Path(videokidnapper.__file__).parent
    for path in root.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        bare = [m.start() for m in re.finditer(r"text=True(?!, encoding=\"utf-8\")", source)]
        assert not bare, f"{path.relative_to(root)} decodes subprocess output with the locale"


def test_unused_subprocess_import_kept_for_monkeypatching():
    assert probe.subprocess is subprocess


def test_probe_is_cached_per_file_version(tmp_path, monkeypatch):
    import os
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"one")
    runs = []

    def run(cmd, **kwargs):
        runs.append(cmd)
        return SimpleNamespace(returncode=0, stderr="", stdout=(
            '{"streams": [{"codec_type": "video", "width": 640, "height": 360}],'
            ' "format": {"duration": "2.5"}}'))

    monkeypatch.setattr(probe.subprocess, "run", run)
    monkeypatch.setattr(probe, "_get_ffprobe", lambda: "ffprobe")
    monkeypatch.setattr(probe, "_info_cache", {})
    first = probe.get_video_info(clip)
    first["width"] = 1   # a caller scribbling on its copy
    assert probe.get_video_info(str(clip))["width"] == 640
    assert len(runs) == 1
    clip.write_bytes(b"changed")
    os.utime(clip, ns=(1, 1))
    probe.get_video_info(clip)
    assert len(runs) == 2, "a changed file is probed again"
