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
