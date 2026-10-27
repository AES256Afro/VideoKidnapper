# SPDX-FileCopyrightText: 2026 AES256Afro <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""The caption font menu offers fonts that really draw.

Fonts were found by guessing the file from the family name, and most
families don't follow that: 19 of the 30 the menu offered came out as
Arial. The index reads each file's own names instead.
"""

import os
import shutil

import pytest

from videokidnapper.utils import font_index


@pytest.fixture(autouse=True)
def fresh_index():
    font_index._reset_for_tests(None)
    yield
    font_index._reset_for_tests(None)


@pytest.mark.parametrize("family, style, want", [
    ("Arial", "Regular", ("Arial", False, False)),
    ("Arial", "Bold Italic", ("Arial", True, True)),
    ("Arial", "Narrow Bold", ("Arial Narrow", True, False)),
    ("Arial", "Black", ("Arial Black", False, False)),
    ("Segoe UI", "Semibold Italic", ("Segoe UI Semibold", False, True)),
    ("Georgia", "Oblique", ("Georgia", False, True)),
])
def test_style_words_split_into_family_bold_and_italic(family, style, want):
    assert font_index._split_style(family, style) == want


def test_lookup_finds_the_style_or_the_nearest_one():
    font_index._reset_for_tests({
        "Agency FB": {(False, False): "AGENCYR.TTF", (True, False): "AGENCYB.TTF"},
    })
    assert font_index.lookup("Agency FB") == "AGENCYR.TTF"
    assert font_index.lookup("agency fb", bold=True) == "AGENCYB.TTF"
    assert font_index.lookup("Agency FB", bold=True, italic=True) == "AGENCYB.TTF"
    assert font_index.lookup("Agency FB", italic=True) == "AGENCYR.TTF"
    assert font_index.lookup("Not Installed") is None


def test_nothing_is_looked_up_before_the_index_is_built():
    assert font_index.families() is None
    assert font_index.lookup("Arial") is None


def test_index_reads_names_from_the_files(tmp_path):
    """A file named nothing like its family is still found by family."""
    from videokidnapper.ui.text_layers import _first_existing, _font_dirs

    real = _first_existing(("DejaVuSans.ttf", "arial.ttf", "Arial.ttf",
                            "LiberationSans-Regular.ttf"), _font_dirs())
    if not real:
        pytest.skip("no known font file on this machine")
    shutil.copy(real, tmp_path / "zz_renamed.ttf")
    (tmp_path / "notes.txt").write_text("not a font")
    (tmp_path / "broken.ttf").write_bytes(b"not a font either")
    index = font_index.build_index([str(tmp_path)])
    (family, faces), = index.items()
    assert os.path.basename(faces[(False, False)]) == "zz_renamed.ttf"
    assert family in ("DejaVu Sans", "Arial", "Liberation Sans")


def test_every_font_in_the_menu_draws_as_itself():
    from videokidnapper.ui.text_layers import (
        _find_font_path, _font_dirs, _get_system_fonts,
    )

    font_index._reset_for_tests(font_index.build_index(_font_dirs()))
    menu = _get_system_fonts()
    fallback = _find_font_path("Definitely Not Installed")
    wrong = [name for name in menu if name not in ("Helvetica",)
             and _find_font_path(name) == fallback
             and font_index.lookup(name) != fallback]
    assert not wrong, wrong[:10]
