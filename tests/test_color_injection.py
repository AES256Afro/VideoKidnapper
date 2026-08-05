# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Colour options must never be able to inject filter graph.

``fontcolor``/``bordercolor``/``shadowcolor``/``boxcolor`` are
interpolated *bare* into the drawtext spec — no surrounding quotes to
contain them. Until 1.8.1 they were passed through untouched, so a
``.vidkid`` project file (which ``project_files.load_document`` accepts
without inspecting layer contents) could set

    "fontcolor": "white,movie=/etc/passwd[bg];[bg]null"

and have the ``,`` terminate the drawtext option, turning the remainder
into extra filter graph. ``movie=`` is an ffmpeg *source* filter that
reads arbitrary local files, so this was file disclosure via a shared
project file, not just a rendering glitch.

Escaping cannot fix a colour — an escaped colour is not a valid colour
and ffmpeg would abort the encode. The values are validated against an
allowlist instead, falling back to the default so a corrupt project
still opens.
"""

import pytest

from videokidnapper.core.ffmpeg.filters import _build_drawtext_filter
from videokidnapper.utils.ffmpeg_escape import sanitize_color


# Every metacharacter that lets a value escape its filter option.
INJECTIONS = [
    "white,movie=/etc/passwd[bg];[bg]null",   # file disclosure
    "white,crop=1:1:0:0",                     # extra filter
    "black@0.7,hflip",
    "white:fontsize=200",                     # extra drawtext option
    "white:textfile=/etc/passwd",             # read a file into the frame
    "white;anullsrc",
    "white[a];[a]null",
    "white'",
    "white\\",
    "white\nfontcolor=red",
]

VALID = [
    "white", "black", "Crimson", "random",
    "#ff0000", "#FF0000AA", "0xff00ff", "0xFF00FF80",
    "white@0.5", "black@0.7", "red@1", "blue@0",
]


@pytest.mark.parametrize("evil", INJECTIONS)
def test_sanitize_color_rejects_injection(evil):
    assert sanitize_color(evil, "white") == "white"


@pytest.mark.parametrize("good", VALID)
def test_sanitize_color_keeps_valid_colors(good):
    assert sanitize_color(good, "white") == good


def test_sanitize_color_handles_none_and_blank():
    assert sanitize_color(None, "white") == "white"
    assert sanitize_color("", "black") == "black"
    assert sanitize_color("   ", "black") == "black"


@pytest.mark.parametrize("field,default", [
    ("fontcolor", "white"),
    ("bordercolor", "black"),
    ("shadowcolor", "black@0.7"),
    ("boxcolor", "black@0.6"),
])
def test_no_color_field_can_inject(field, default):
    """End-to-end: none of the four colour fields may add filter graph."""
    layer = {
        "text": "hi",
        # Force every optional block to render so each colour is emitted.
        "borderw": 2, "shadowx": 1, "shadowy": 1, "box": 1,
        field: "white,movie=/etc/passwd[bg];[bg]null",
    }
    spec = _build_drawtext_filter(layer)
    assert "movie=" not in spec
    assert "/etc/passwd" not in spec
    assert f"{field}={default}" in spec


def test_drawtext_option_count_is_stable_under_attack():
    """A rejected colour must not change the shape of the filter spec.

    Counting top-level ':' separators catches an injection that slips
    through without matching the string assertions above.
    """
    benign = _build_drawtext_filter({"text": "hi", "fontcolor": "white"})
    attacked = _build_drawtext_filter(
        {"text": "hi", "fontcolor": "white,movie=/etc/passwd[b];[b]null"},
    )
    assert benign == attacked
