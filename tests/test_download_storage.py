# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Where downloads are kept, and what the exit cleanup may delete.

Downloads used to stay in ``~/.videokidnapper_temp`` and the app deleted
that whole folder on exit, so the video being edited (and any sticker
pasted from the clipboard) was gone the next time its project opened.
Finished files now live in ``config.MEDIA_DIR``; the exit cleanup only
removes what an unfinished download or a screen recording leaves.

No network: yt-dlp is never asked to fetch anything here.
"""

import io

import pytest

from videokidnapper import config
from videokidnapper.core import downloader


@pytest.fixture
def dirs(monkeypatch, tmp_path):
    temp, media = tmp_path / "temp", tmp_path / "media"
    monkeypatch.setattr(config, "TEMP_DIR", temp)
    monkeypatch.setattr(config, "MEDIA_DIR", media)
    return temp, media


def test_exit_cleanup_keeps_finished_media(dirs):
    temp, _media = dirs
    temp.mkdir()
    kept = ["Old_download.mp4", "vk_clip_abc.png", "Some clip.webm"]
    gone = ["Clip.mp4.part", "Clip.mp4.part-Frag12", "Clip.mp4.ytdl",
            "Clip.temp.mp4", "Clip.f137.mp4", "Clip.f140.m4a"]
    for name in kept + gone:
        (temp / name).write_bytes(b"x")
    frames = temp / "record_1a2b3c4d"
    frames.mkdir()
    (frames / "frame_000000.png").write_bytes(b"x")

    downloader.cleanup_temp()

    assert sorted(p.name for p in temp.iterdir()) == sorted(kept)


def test_exit_cleanup_without_a_temp_folder(dirs):
    downloader.cleanup_temp()   # must not raise


def test_downloads_finish_in_the_media_folder(dirs):
    temp, media = dirs
    opts, _platform = downloader._build_ydl_opts(
        "https://youtu.be/x", None, lambda d: None)
    assert opts["paths"] == {"home": str(media), "temp": str(temp)}
    assert "/" not in opts["outtmpl"] and "\\" not in opts["outtmpl"]


class _FakeResponse(io.BytesIO):
    def __init__(self, body, ctype):
        super().__init__(body)
        self.headers = {"Content-Type": ctype, "Content-Length": str(len(body))}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_reddit_direct_media_is_kept(dirs, monkeypatch):
    import urllib.request

    temp, media = dirs
    monkeypatch.setattr(urllib.request, "urlopen",
                        lambda *_a, **_k: _FakeResponse(b"GIF89a...", "image/gif"))
    (media).mkdir()
    (media / "cat.gif").write_bytes(b"an earlier download")

    path = downloader._download_direct_media("https://i.redd.it/cat.gif")

    assert path == str(media / "cat (2).gif")
    assert (media / "cat (2).gif").read_bytes() == b"GIF89a..."
    assert (media / "cat.gif").read_bytes() == b"an earlier download"
    assert list(temp.iterdir()) == []
