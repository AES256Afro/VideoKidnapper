# SPDX-FileCopyrightText: 2026 AES256Afro <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
import pytest

from videokidnapper.core.downloader import detect_platform


@pytest.mark.parametrize("url, expected", [
    ("https://www.youtube.com/watch?v=abc",           "YouTube"),
    ("https://youtu.be/abc",                          "YouTube"),
    ("https://music.youtube.com/watch?v=abc",         "YouTube"),
    ("https://m.youtube.com/watch?v=abc",             "YouTube"),
    ("https://www.instagram.com/reel/C1/",            "Instagram"),
    ("https://bsky.app/profile/alice/post/x",         "Bluesky"),
    ("https://twitter.com/u/status/1",                "Twitter/X"),
    ("https://x.com/u/status/1",                      "Twitter/X"),
    ("https://mobile.twitter.com/u/status/1",         "Twitter/X"),
    ("https://www.reddit.com/r/v/comments/abc/t/",    "Reddit"),
    ("https://redd.it/abc",                           "Reddit"),
    ("https://v.redd.it/xyz",                         "Reddit"),
    ("https://old.reddit.com/r/videos/",              "Reddit"),
    ("https://www.facebook.com/watch?v=123",          "Facebook"),
    ("https://facebook.com/user/videos/123",          "Facebook"),
    ("https://fb.watch/xyz",                          "Facebook"),
    ("https://m.facebook.com/reel/123",               "Facebook"),
    ("https://fb.com/user/videos/123",                "Facebook"),
    ("https://example.com/video.mp4",                 None),
    ("",                                              None),
    (None,                                            None),
])
def test_detect_platform(url, expected):
    assert detect_platform(url) == expected


@pytest.mark.parametrize("url", [
    "https://www.dropbox.com/s/abc123/clip.mp4?dl=0",
    "https://www.netflix.com/watch/8000",
    "https://www.xbox.com/en-US/play",
    "https://www.roblox.com/games/1",
    "https://notyoutube.com/watch?v=1",
    "https://example.com/?next=https://youtube.com/watch?v=1",
    "https://youtube.com.example.net/watch?v=1",
])
def test_other_sites_are_not_mistaken_for_a_platform(url):
    """Matching "x.com/" anywhere in the link made Dropbox, Netflix and
    Xbox links "Twitter/X": the X download format, and "This X/Twitter
    post is private" for their errors."""
    assert detect_platform(url) is None


@pytest.mark.parametrize("url, expected", [
    ("youtu.be/abc",                       "YouTube"),
    ("www.instagram.com/reel/C1/",         "Instagram"),
    ("HTTPS://X.COM/u/status/1",           "Twitter/X"),
    ("https://user@www.reddit.com:443/r/", "Reddit"),
    ("https://www.youtube-nocookie.com/embed/abc", "YouTube"),
])
def test_hosts_without_scheme_or_with_extras(url, expected):
    assert detect_platform(url) == expected
