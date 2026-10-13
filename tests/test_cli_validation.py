# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""The CLI rejects option combinations the encoder cannot honour."""

import pytest

from videokidnapper import cli


def _run(argv, monkeypatch, tmp_path, calls=None):
    src = tmp_path / "in.mp4"
    src.write_bytes(b"x")
    import videokidnapper.core.ffmpeg_backend as backend

    monkeypatch.setattr(backend, "get_video_info", lambda p: {"duration": 4.0})

    def fake(kind):
        def encode(src, start, end, quality, out, **kw):
            if calls is not None:
                calls.append((kind, out, kw["options"]))
            return out
        return encode

    monkeypatch.setattr(backend, "trim_to_video", fake("video"))
    monkeypatch.setattr(backend, "trim_to_gif", fake("gif"))
    monkeypatch.setattr("videokidnapper.utils.file_naming.generate_export_path",
                        lambda prefix, ext, **kw: tmp_path / f"{prefix}.{ext}")
    return cli._cli_main(cli._parse_args(["--file", str(src), *argv]))


def test_audio_only_writes_an_mp3(monkeypatch, tmp_path):
    calls = []
    assert _run(["--audio-only"], monkeypatch, tmp_path, calls) == 0
    assert str(calls[0][1]).endswith(".mp3")


def test_gif_with_audio_only_is_refused(monkeypatch, tmp_path, capsys):
    assert _run(["--format", "GIF", "--audio-only"], monkeypatch, tmp_path) == 2
    assert "cannot be combined" in capsys.readouterr().err


@pytest.mark.parametrize("speed", ["0", "-1", "0.1", "10"])
def test_speed_out_of_range_is_refused(monkeypatch, tmp_path, capsys, speed):
    assert _run(["--speed", speed], monkeypatch, tmp_path) == 2
    assert "--speed" in capsys.readouterr().err


def test_unreadable_file_is_an_error_not_a_traceback(monkeypatch, tmp_path, capsys):
    import videokidnapper.core.ffmpeg_backend as backend
    from videokidnapper.core.ffmpeg.probe import ProbeError

    src = tmp_path / "in.mp4"
    src.write_bytes(b"x")

    def broken(path):
        raise ProbeError("ffprobe exited 1: Invalid data")

    monkeypatch.setattr(backend, "get_video_info", broken)
    assert cli._cli_main(cli._parse_args(["--file", str(src)])) == 1
    assert "cannot read" in capsys.readouterr().err
