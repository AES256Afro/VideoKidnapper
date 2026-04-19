# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Platform-preset registry contract.

These presets are referenced by settings (``platform_preset`` key) and by
the TrimTab Platform dropdown, so every entry must resolve to a valid
Quality / Format / aspect triple that the downstream code already
understands — otherwise picking one in the dropdown silently corrupts
the export options.
"""

import pytest

from videokidnapper.config import EXPORT_FORMATS, PRESETS
from videokidnapper.ui.export_options import ASPECT_CHOICES
from videokidnapper.ui.platform_presets import (
    PLATFORM_CHOICES,
    PLATFORM_PRESETS,
    get_preset,
)


def test_custom_is_first_and_noop():
    assert PLATFORM_CHOICES[0] == "Custom"
    assert PLATFORM_PRESETS["Custom"] is None
    assert get_preset("Custom") is None


def test_unknown_preset_returns_none():
    assert get_preset("NotAPreset") is None
    assert get_preset("") is None


@pytest.mark.parametrize("name", [n for n in PLATFORM_CHOICES if n != "Custom"])
def test_preset_fields_are_valid(name):
    preset = get_preset(name)
    assert preset is not None, name
    assert preset["quality"] in PRESETS, f"{name} quality"
    assert preset["format"] in EXPORT_FORMATS, f"{name} format"
    assert preset["aspect"] in ASPECT_CHOICES, f"{name} aspect"


def test_shorts_reels_and_tiktok_are_vertical():
    for name in ("YouTube Shorts", "Instagram Reel", "Instagram Story", "TikTok"):
        assert get_preset(name)["aspect"] == "9:16", name


def test_instagram_post_is_square():
    assert get_preset("Instagram Post")["aspect"] == "1:1"


def test_discord_8mb_uses_low_quality():
    # The 8 MB free-tier cap only fits cleanly at Low; higher tiers
    # regularly overshoot even for short clips.
    assert get_preset("Discord (8 MB)")["quality"] == "Low"


def test_slack_uses_gif():
    assert get_preset("Slack GIF")["format"] == "GIF"


def test_no_duplicate_names():
    assert len(PLATFORM_CHOICES) == len(set(PLATFORM_CHOICES))
