# SPDX-FileCopyrightText: 2026 AES256Afro <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Installed fonts, by the names people pick them by.

Captions are drawn from a font *file*, in the preview and by ffmpeg's
drawtext, and the file used to be found by guessing its name from the
family ("Arial" -> arial.ttf). Most families don't follow that. Of the
30 the caption font menu offered on a stock Windows 11, 19 quietly came
out as Arial, and the rest of the installed fonts couldn't be picked at
all. This reads each font file's own family and style names once, on a
worker thread (about a second for 340 files), so every family the menu
lists is one that really draws.

A file's style words that aren't bold or italic become part of the
family: Arial's "Narrow Bold" face is the bold of "Arial Narrow", which
is how Windows lists it too. Only the first face of a ``.ttc`` is used,
as that is the one drawtext's ``fontfile`` draws.
"""

import os
import threading

_UPRIGHT = {"regular", "normal", "book", "roman", "plain"}
_BOLD = {"bold"}
_ITALIC = {"italic", "oblique"}
_EXTS = (".ttf", ".otf", ".ttc")

_lock = threading.Lock()
_index = None      # family -> {(bold, italic): path}, once built
_folded = None     # family.lower() -> family
_started = False


def _split_style(family, style):
    """``("Arial", "Narrow Bold")`` -> ``("Arial Narrow", True, False)``."""
    words = (style or "").split()
    lower = [w.lower() for w in words]
    bold = any(w in _BOLD for w in lower)
    italic = any(w in _ITALIC for w in lower)
    rest = [w for w, low in zip(words, lower)
            if low not in _BOLD | _ITALIC | _UPRIGHT]
    if rest:
        family = f"{family} {' '.join(rest)}"
    return family, bold, italic


def build_index(dirs):
    """Read every font file under ``dirs``: family -> {(bold, italic): path}.

    The first file found for a family and style wins, so earlier
    directories take precedence, as in the name-based lookup.
    """
    from PIL import ImageFont

    index = {}
    for directory in dirs:
        if not directory or not os.path.isdir(directory):
            continue
        for root, _subdirs, files in os.walk(directory):
            for name in sorted(files):
                if not name.lower().endswith(_EXTS):
                    continue
                path = os.path.join(root, name)
                try:
                    family, style = ImageFont.truetype(path, 12).getname()
                except Exception:
                    continue
                # macOS keeps private system faces under dotted names.
                if not family or family.startswith("."):
                    continue
                family, bold, italic = _split_style(family, style)
                index.setdefault(family, {}).setdefault((bold, italic), path)
    return index


def start(dirs):
    """Build the index on a worker thread, once per run."""
    global _started
    with _lock:
        if _started:
            return
        _started = True

    def work():
        global _index, _folded
        try:
            index = build_index(dirs)
        except Exception:
            index = {}
        with _lock:
            _index = index
            _folded = {family.lower(): family for family in index}

    threading.Thread(target=work, daemon=True, name="font-index").start()


def families():
    """Every indexed family, sorted; None until the index is built."""
    with _lock:
        index = _index
    if index is None:
        return None
    return sorted(index, key=str.lower)


def lookup(family, bold=False, italic=False):
    """The file for ``family`` in that style, or None.

    None when the family isn't installed or the index isn't built yet;
    the caller then falls back to guessing from the name. A style the
    family doesn't have falls back to the nearest it does, as Windows
    would without synthesising one.
    """
    with _lock:
        index, folded = _index, _folded
    if not index or not family:
        return None
    faces = index.get(family)
    if faces is None:
        name = folded.get(str(family).lower())
        faces = index.get(name) if name else None
    if not faces:
        return None
    bold, italic = bool(bold), bool(italic)
    for key in ((bold, italic), (bold, False), (False, italic), (False, False)):
        if key in faces:
            return faces[key]
    return next(iter(faces.values()))


def _reset_for_tests(index=None):
    global _index, _folded, _started
    with _lock:
        _index = index
        _folded = {f.lower(): f for f in index} if index is not None else None
        _started = index is not None
