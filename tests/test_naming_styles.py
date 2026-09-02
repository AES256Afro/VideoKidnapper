# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Exports are named after the video, and the style is configurable.

Every export used to be ``VidKid_<mode>_<date>_<time>.<ext>``, so a
folder of clips was a wall of identical-looking names distinguished
only by a timestamp. Names now come from the source title by default.

Video titles are hostile input for a filesystem — path separators,
control characters, Windows device names, emoji, 300-character
ramblings — so most of what is tested here is the cleaning.
"""

import sys
from datetime import datetime

import pytest

from videokidnapper.utils.file_naming import (
    FALLBACK_STEM,
    LABEL_TO_STYLE,
    NAMING_STYLES,
    _stem_from,
    build_base_name,
    generate_export_path,
    sanitize_filename_component,
)


WHEN = datetime(2026, 9, 2, 14, 30, 22)


# ------------------------------------------------------------- sanitizing

@pytest.mark.parametrize("raw,expected", [
    ('a<b>c:d"e|f?g*h', "abcdefgh"),      # every Windows-illegal character
    ("  ..hidden..  ", "hidden"),          # leading dot hides on POSIX
    ("trailing dots...", "trailing dots"),  # Windows strips these silently
    ("multiple   spaces", "multiple spaces"),
    ("日本語のタイトル", "日本語のタイトル"),        # non-ASCII must survive
])
def test_sanitize(raw, expected):
    assert sanitize_filename_component(raw) == expected


@pytest.mark.parametrize("name", ["CON", "con", "NUL", "COM1", "LPT9"])
def test_windows_device_names_are_defused(name):
    """"CON.mp4" is as unopenable as "CON" on Windows."""
    assert sanitize_filename_component(name) != name
    assert sanitize_filename_component(name).upper().rstrip("_") == name.upper()


def test_control_and_formatting_characters_are_removed():
    assert "​" not in sanitize_filename_component("a​b")
    assert "\x07" not in sanitize_filename_component("a\x07b")
    assert sanitize_filename_component("a\nb") == "a b"


def test_long_titles_are_truncated_at_a_word_boundary():
    title = "The quick brown fox jumps over the lazy dog " * 5
    out = sanitize_filename_component(title)
    assert len(out) <= 80
    assert not out.endswith(" ")
    # Cut between words, not mid-word, when that leaves enough text.
    assert out.split()[-1] in title.split()


def test_unusable_input_yields_empty_so_callers_can_fall_back():
    for raw in ("", None, "   ", "...", "///", "\x00\x01"):
        assert sanitize_filename_component(raw) == ""


# ------------------------------------------------ titles are not paths

def test_a_slash_in_a_title_is_stripped_not_split():
    """The bug this test exists for: `Path("AC/DC - x").name` returns
    "DC - x", silently losing the first half. Band names, "either/or"
    and dates all carry slashes, so that would be routine data loss."""
    assert _stem_from("AC/DC — Back in Black") == "ACDC — Back in Black"
    assert _stem_from("either/or") == "eitheror"


def test_media_extension_is_stripped_from_a_filename():
    assert _stem_from("My Clip.mp4") == "My Clip"
    assert _stem_from("song.MP3") == "song"


def test_a_dot_that_is_not_an_extension_survives():
    assert _stem_from("Episode 3.Return of the Thing") == \
        "Episode 3.Return of the Thing"
    assert _stem_from("archive.tar.gz") == "archive.tar.gz"


def test_a_real_path_is_reduced_to_its_stem(tmp_path):
    """A caller passing a path instead of a title is an easy slip."""
    real = tmp_path / "holiday clip.mov"
    real.write_text("")
    assert _stem_from(str(real)) == "holiday clip"


# ------------------------------------------------------------- the styles

@pytest.mark.parametrize("style,expected", [
    ("title",      "My Great Clip"),
    ("title_date", "My Great Clip_20260902"),
    ("title_time", "My Great Clip_20260902_143022"),
    ("timestamp",  "VidKid_trim_20260902_143022"),
])
def test_each_style(style, expected):
    assert build_base_name("trim", "My Great Clip.mp4",
                           style=style, when=WHEN) == expected


@pytest.mark.parametrize("style", list(NAMING_STYLES))
def test_no_style_produces_an_empty_or_unsafe_name(style):
    for source in (None, "", "???", "CON", "a" * 300):
        name = build_base_name("trim", source, style=style, when=WHEN)
        assert name, f"{style} produced an empty name for {source!r}"
        assert not any(c in name for c in '<>:"/\\|?*')
        assert name == name.strip(". ")


def test_missing_title_falls_back_rather_than_producing_a_bare_extension():
    assert build_base_name("trim", None, style="title", when=WHEN) == FALLBACK_STEM


def test_labels_and_keys_round_trip():
    """The dropdown stores a label; the setting stores a key."""
    for key, (label, _fn) in NAMING_STYLES.items():
        assert LABEL_TO_STYLE[label] == key


def test_an_unknown_style_falls_back_instead_of_raising():
    """A settings file edited by hand, or written by an older build."""
    assert build_base_name("trim", "Clip", style="nonsense", when=WHEN)


# ---------------------------------------------------------------- on disk

def test_path_uses_the_title(tmp_path):
    out = generate_export_path("trim", "mp4", base_dir=tmp_path,
                               source_name="Holiday Video", style="title")
    assert out.name == "Holiday Video.mp4"
    assert out.parent == tmp_path


def test_collisions_get_a_counter(tmp_path):
    """Now the common case, not the rare one: with title-based names a
    second export of the same clip collides every time."""
    first = generate_export_path("trim", "gif", base_dir=tmp_path,
                                 source_name="Clip", style="title")
    first.write_text("")
    second = generate_export_path("trim", "gif", base_dir=tmp_path,
                                  source_name="Clip", style="title")
    assert first.name == "Clip.gif"
    assert second.name == "Clip_1.gif"
    second.write_text("")
    third = generate_export_path("trim", "gif", base_dir=tmp_path,
                                 source_name="Clip", style="title")
    assert third.name == "Clip_2.gif"


def test_extension_may_be_dotted_or_bare(tmp_path):
    for ext in ("mp4", ".mp4", "MP4"):
        assert generate_export_path("trim", ext, base_dir=tmp_path,
                                    source_name="X").suffix == ".mp4"


def test_creates_missing_base_dir(tmp_path):
    nested = tmp_path / "deep" / "export"
    generate_export_path("trim", "mp4", base_dir=nested, source_name="X")
    assert nested.exists()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX path semantics")
def test_result_never_escapes_the_base_dir(tmp_path):
    """A title is data, not a path — it must not be able to traverse."""
    for hostile in ("../../etc/passwd", "..", "/absolute/thing", "a/../../b"):
        out = generate_export_path("trim", "mp4", base_dir=tmp_path,
                                   source_name=hostile, style="title")
        assert out.resolve().parent == tmp_path.resolve(), hostile
