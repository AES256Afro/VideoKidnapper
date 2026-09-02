# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Font lookup has to work off Windows.

`_find_font_path` was Windows-only by construction: a hardcoded
`C:\\Windows\\Fonts`, Windows filenames, and a fallback to `arial.ttf`
inside that same directory. On macOS and Linux nothing ever matched, so
it always returned a path that did not exist.

The consequences were not subtle. The preview canvas caught the
resulting `truetype()` failure and fell back to Pillow's
`load_default()` bitmap face, which ignores the requested size — so
every caption drew at ~8 px tall no matter what. Measured before the
fix, on macOS:

    fontsize= 12 -> rendered 24x 8 px
    fontsize= 24 -> rendered 24x 8 px
    fontsize= 48 -> rendered 24x 8 px
    fontsize= 96 -> rendered 24x 8 px

The font-size control did nothing visible, on a captioning app, on the
platform that had just absorbed a release cycle of packaging work.
"""

import os
import sys

import pytest

from videokidnapper.ui.text_layers import (
    _FONT_FILES,
    _find_font_path,
    _font_dirs,
)


# --------------------------------------------------------------- discovery

def test_search_dirs_are_platform_appropriate():
    dirs = _font_dirs()
    assert dirs, "no font directories for this platform"
    joined = " ".join(dirs)
    if sys.platform == "darwin":
        assert "/System/Library/Fonts" in joined
    elif sys.platform == "win32":
        assert "Fonts" in joined
    else:
        assert "/usr/share/fonts" in joined or ".fonts" in joined


@pytest.mark.skipif(
    sys.platform == "win32", reason="the Windows path was always fine",
)
def test_resolves_to_a_file_that_exists():
    """The whole bug in one assertion."""
    path = _find_font_path("Arial")
    assert os.path.exists(path), (
        f"{path!r} does not exist — the preview will fall back to a "
        "bitmap font and ignore the requested size"
    )


@pytest.mark.skipif(sys.platform == "win32", reason="see above")
@pytest.mark.parametrize("name", ["Arial", "Impact", "Georgia", "Verdana"])
def test_common_fonts_resolve(name):
    assert os.path.exists(_find_font_path(name))


@pytest.mark.skipif(sys.platform == "win32", reason="see above")
def test_unknown_font_still_yields_something_usable():
    """An unknown name must land on a real face, not a dead path."""
    assert os.path.exists(_find_font_path("Definitely Not Installed"))


@pytest.mark.skipif(
    sys.platform != "darwin", reason="mono substitutes are platform-specific",
)
def test_monospace_does_not_fall_back_to_a_proportional_face():
    """Consolas is absent on macOS; landing on Arial is a visibly wrong
    answer for a font chosen because it is monospaced."""
    resolved = os.path.basename(_find_font_path("Consolas")).lower()
    assert "arial" not in resolved, f"Consolas resolved to {resolved!r}"


def test_every_mapping_lists_a_cross_platform_option():
    """Each logical font needs more than its Windows filename, or the
    lookup silently degrades again off Windows."""
    thin = [name for name, files in _FONT_FILES.items() if len(files) < 2]
    assert not thin, f"only one candidate filename for: {thin}"


# ------------------------------------------------- the override tests use

def test_explicit_fonts_dir_is_still_honoured(tmp_path):
    """The existing suite drives resolution against a temp directory."""
    (tmp_path / "arial.ttf").write_bytes(b"x")
    assert _find_font_path("Arial", fonts_dir=str(tmp_path)) == str(
        tmp_path / "arial.ttf"
    )


def test_missing_font_in_an_explicit_dir_keeps_the_old_return_shape(tmp_path):
    """Callers have always received a path back, even a non-existent one."""
    result = _find_font_path("Arial", fonts_dir=str(tmp_path))
    assert result.endswith("arial.ttf")
    assert str(tmp_path) in result


# ------------------------------------------------------- rendering effect

@pytest.mark.skipif(sys.platform == "win32", reason="see above")
def test_preview_text_actually_scales_with_fontsize():
    """The user-visible symptom: identical output at every size."""
    Image = pytest.importorskip("PIL.Image")
    ImageDraw = pytest.importorskip("PIL.ImageDraw")
    ImageFont = pytest.importorskip("PIL.ImageFont")

    path = _find_font_path("Arial")
    draw = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    heights = []
    for size in (12, 24, 48, 96):
        font = ImageFont.truetype(path, size)
        box = draw.multiline_textbbox((0, 0), "XXXX", font=font, spacing=0)
        heights.append(box[3] - box[1])

    assert heights == sorted(heights), heights
    assert len(set(heights)) == len(heights), (
        f"text height did not change with font size: {heights} — the "
        "bitmap fallback is back"
    )
