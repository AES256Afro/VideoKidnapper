# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""looks_like_media_url — the app-level Ctrl+V router's decision function."""

import pytest

from videokidnapper.utils.urltools import looks_like_media_url


@pytest.mark.parametrize("text", [
    "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "http://example.com/clip.gif",
    "https://x.com/user/status/123",
    "www.reddit.com/r/gifs/comments/abc",
    "  https://bsky.app/profile/foo/post/bar  ",   # surrounding whitespace ok
    "HTTPS://YOUTU.BE/ABC",                        # case-insensitive scheme
])
def test_links_are_recognized(text):
    assert looks_like_media_url(text)


@pytest.mark.parametrize("text", [
    "",
    None,
    "hello world",
    "check this out: https://youtu.be/abc",        # sentence, not a bare link
    "https://a.com\nhttps://b.com",                # multi-line clipboard
    "C:\\Users\\chris\\video.mp4",                 # file path
    "ftp://example.com/file",                      # not a web link
    "youtube.com/watch?v=abc",                     # no scheme, no www
])
def test_non_links_fall_through(text):
    assert not looks_like_media_url(text)
