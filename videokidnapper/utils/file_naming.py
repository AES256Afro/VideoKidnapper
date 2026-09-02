# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Export file-name generation.

Every export used to be ``VidKid_<mode>_<YYYYMMDD>_<HHMMSS>.<ext>``, so
a folder of clips read as one indistinguishable wall of ``VidKid_trim_``
and the only way to tell them apart was the timestamp. Names now derive
from the source video's title by default, and the style is a setting.

Adding a style means adding one entry to :data:`NAMING_STYLES`; the
settings value, the dropdown, and the generator all read from it.
"""
import os
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional, Union

from videokidnapper.config import DOWNLOADS_DIR
from videokidnapper.utils import settings


PathLike = Union[str, Path]

#: Settings key holding the chosen style.
SETTING_KEY = "naming_style"

#: Used when a title is unavailable or sanitizes away to nothing.
FALLBACK_STEM = "clip"

#: Keep well clear of the ~255-byte per-component limit while leaving
#: room for the mode, timestamp, collision counter and extension.
MAX_STEM_LENGTH = 80

# Characters no mainstream filesystem will accept in a component, plus
# the ASCII control range. Windows is the strictest, so it sets the bar
# for everyone — a name that works there works on macOS and Linux.
_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

# Reserved device names on Windows, matched without extension and
# case-insensitively. "CON.mp4" is as unusable as "CON".
_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def sanitize_filename_component(text: Optional[str],
                                max_length: int = MAX_STEM_LENGTH) -> str:
    """Turn arbitrary text into something safe to use as a file name.

    Video titles are the motivating input and they are genuinely hostile
    to filesystems: ``AC/DC — Back in Black (Official Video) 🎸`` carries
    a path separator, an em dash, and an emoji. Non-ASCII is kept — an
    accented or CJK title should survive intact — but anything that
    would break a path, confuse a shell, or collide with a Windows
    device name is removed.

    Returns ``""`` when nothing usable is left, so callers can fall back
    rather than writing a file called ``.mp4``.
    """
    if not text:
        return ""

    # Normalise first: composed forms behave better across filesystems,
    # and macOS will re-normalise anyway.
    cleaned = unicodedata.normalize("NFC", str(text))

    # Line breaks and tabs become spaces first: they are control
    # characters, so the filter below would delete them outright and
    # weld the surrounding words together ("line one\nline two" ->
    # "line oneline two").
    cleaned = re.sub(r"[\t\n\r\f\v]+", " ", cleaned)

    # Drop the remaining control and formatting characters (category
    # C*) — zero-width joiners and bidi overrides survive `_ILLEGAL`
    # but make for names that cannot be typed or safely displayed.
    cleaned = "".join(
        ch for ch in cleaned if not unicodedata.category(ch).startswith("C")
    )

    cleaned = _ILLEGAL.sub("", cleaned)
    # Collapse runs of whitespace, including the exotic kinds titles use.
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    # Leading dots hide the file on POSIX; trailing dots and spaces are
    # silently stripped by Windows, which turns "a." into "a".
    cleaned = cleaned.strip(". ")

    if len(cleaned) > max_length:
        # Prefer cutting at a word boundary so truncation reads as a
        # shortened title rather than a corrupted one.
        cut = cleaned[:max_length]
        spaced = cut.rsplit(" ", 1)[0]
        cleaned = (spaced if len(spaced) >= max_length // 2 else cut).strip(". ")

    if cleaned.upper() in _RESERVED:
        cleaned = f"{cleaned}_"

    return cleaned


#: Extensions worth stripping when a caller hands over a filename
#: rather than a bare title. Deliberately a closed list: a title like
#: "Episode 3.Return" must not lose its tail to a generic rule.
_MEDIA_EXTS = {
    "mp4", "mov", "mkv", "webm", "avi", "m4v", "flv", "wmv", "mpg",
    "mpeg", "gif", "mp3", "m4a", "wav", "opus", "ogg", "webp",
}


def _stem_from(source_name: Optional[str]) -> str:
    """The title part of ``source_name``, with any media extension gone.

    Note the ordering: sanitize FIRST, then strip the extension. Running
    this through ``pathlib`` instead is the obvious approach and it is
    wrong — a title is not a path, and ``Path("AC/DC - Back in
    Black").name`` silently returns ``"DC - Back in Black"``. Titles
    containing a slash are common enough (band names, "either/or",
    dates) that the mangling would be a quiet, regular data loss.
    """
    if not source_name:
        return ""
    raw = str(source_name)
    # Callers are expected to pass a title, but a real path is an easy
    # slip and mangles badly under the sanitize-first rule above. If it
    # actually points at a file, take its stem before cleaning.
    try:
        if os.sep in raw and Path(raw).exists():
            raw = Path(raw).stem
    except (OSError, ValueError):
        pass
    cleaned = sanitize_filename_component(raw)
    head, dot, tail = cleaned.rpartition(".")
    if dot and head and tail.lower() in _MEDIA_EXTS:
        cleaned = head.strip()
    return cleaned


def _title(mode: str, stem: str, when: datetime) -> str:
    return stem or FALLBACK_STEM


def _title_date(mode: str, stem: str, when: datetime) -> str:
    return f"{stem or FALLBACK_STEM}_{when.strftime('%Y%m%d')}"


def _title_time(mode: str, stem: str, when: datetime) -> str:
    return f"{stem or FALLBACK_STEM}_{when.strftime('%Y%m%d_%H%M%S')}"


def _legacy(mode: str, stem: str, when: datetime) -> str:
    return f"VidKid_{mode}_{when.strftime('%Y%m%d_%H%M%S')}"


#: key -> (menu label, builder). Order is the order shown in the UI.
NAMING_STYLES: "dict[str, tuple[str, Callable[[str, str, datetime], str]]]" = {
    "title":      ("Video title", _title),
    "title_date": ("Video title + date", _title_date),
    "title_time": ("Video title + date & time", _title_time),
    "timestamp":  ("VidKid + timestamp", _legacy),
}

DEFAULT_STYLE = "title"

#: Label -> key, for translating a dropdown selection back to a setting.
LABEL_TO_STYLE = {label: key for key, (label, _fn) in NAMING_STYLES.items()}


def current_style() -> str:
    """The configured style, falling back when the setting is unusable."""
    value = settings.get(SETTING_KEY, DEFAULT_STYLE)
    return value if value in NAMING_STYLES else DEFAULT_STYLE


def build_base_name(mode: str,
                    source_name: Optional[str] = None,
                    style: Optional[str] = None,
                    when: Optional[datetime] = None) -> str:
    """Assemble the stem (no extension) for one export."""
    style = style if style in NAMING_STYLES else current_style()
    stem = _stem_from(source_name)
    when = when or datetime.now()
    name = NAMING_STYLES[style][1](mode, stem, when)
    # A builder can still produce something unusable if `mode` is odd.
    return sanitize_filename_component(name, MAX_STEM_LENGTH + 24) or FALLBACK_STEM


def generate_export_path(
    mode: str,
    extension: str,
    base_dir: Optional[PathLike] = None,
    source_name: Optional[str] = None,
    style: Optional[str] = None,
) -> Path:
    """Return a new, unique export path under ``base_dir``.

    ``mode`` is the export kind (``trim``, ``cli``, ``record``,
    ``trim_concat``) and is only shown by the timestamp style.
    ``source_name`` is the video's **title** (or a bare filename) — the
    title styles derive the name from it and fall back to ``clip``
    without one. Pass a title, not a path: a slash in a title is
    stripped, not treated as a separator, because titles containing one
    are common. An actual existing path is detected and reduced to its
    stem as a convenience.
    ``extension`` may be dotted or bare.

    A ``_n`` suffix is appended on collision. That used to be rare
    because names carried a timestamp to the second; with title-based
    names a second export of the same clip collides every time, so this
    path is now the common one rather than the exception.
    """
    resolved_base: Path = Path(base_dir) if base_dir else DOWNLOADS_DIR
    resolved_base.mkdir(parents=True, exist_ok=True)
    base_name = build_base_name(mode, source_name, style)
    ext = extension.lower().lstrip(".")
    output = resolved_base / f"{base_name}.{ext}"
    counter = 1
    while output.exists():
        output = resolved_base / f"{base_name}_{counter}.{ext}"
        counter += 1
    return output
