import pytest

from videokidnapper.utils import share


@pytest.mark.parametrize("platform", [
    "YouTube", "Instagram", "Bluesky", "Twitter/X", "Reddit", "Facebook",
])
def test_every_platform_has_share_target(platform):
    url, instructions = share.build_share_url(platform, "/tmp/clip.mp4")
    assert url.startswith("http")
    assert instructions


def test_unknown_platform_raises():
    with pytest.raises(ValueError):
        share.build_share_url("MySpace", "/tmp/clip.mp4")


def test_facebook_url_intent_encoded():
    out = share.build_url_intent("Facebook", "https://example.com/a?b=c")
    assert out.startswith("https://www.facebook.com/sharer/sharer.php?u=")
    # Query should be URL-encoded so the sharer site reads it as a single param
    assert "%3A" in out or "%2F" in out


def test_twitter_url_intent():
    out = share.build_url_intent("Twitter/X", "https://example.com/clip")
    assert "intent/tweet" in out
    assert "url=" in out


def test_reddit_url_intent():
    out = share.build_url_intent("Reddit", "https://example.com/clip")
    assert "reddit.com/submit" in out
    assert "url=" in out


def test_url_intent_unknown_returns_none():
    assert share.build_url_intent("Bluesky", "https://example.com") is None


def test_share_targets_matches_platform_colors():
    """Every share target should have a matching theme brand color + chip."""
    from videokidnapper.ui import theme as T
    for platform in share.SHARE_TARGETS:
        assert platform in T.PLATFORM_COLORS, f"Missing color for {platform}"
        assert platform in T.PLATFORM_GLYPHS, f"Missing glyph for {platform}"
