# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Pull images out of the system clipboard.

The OS clipboard can hold an image in two shapes depending on where it
came from:

1. **Bitmap data** — e.g. a screenshot, a copy from a browser's image
   context menu, or a "Copy image" from a chat app. On Windows / macOS
   PIL surfaces this as an :class:`Image` object.
2. **A list of file paths** — e.g. Explorer / Finder "Copy" on an image
   file on disk. PIL returns this as a list of strings.

The empty case (text-only, nothing copied yet, clipboard unreachable on
a headless Linux, …) returns ``None`` so callers can toast the user
without special-casing exceptions.

Animated GIFs: when a file path is on the clipboard, we return it
as-is so the overlay encoder sees the real multi-frame file. When
bitmap data is on the clipboard it's already been flattened to a
still frame — there is no way to recover the animation from that.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Optional


SUPPORTED_IMAGE_EXTS = frozenset({".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"})


def grab_clipboard_image(temp_dir: str | os.PathLike[str] | None = None) -> Optional[Path]:
    """Return a :class:`Path` to an image sourced from the clipboard, or ``None``.

    Bitmap data is saved as PNG into ``temp_dir`` (defaults to the app
    temp dir); file-path clipboards return the first supported image
    path that actually exists on disk.

    Never raises — any failure (PIL missing, clipboard unreachable,
    write permission denied) resolves to ``None`` so the caller can
    treat all "no image" cases uniformly. The one thing we do NOT do
    is log the failure here; the UI is a better place for that.
    """
    try:
        from PIL import ImageGrab
    except ImportError:
        return None

    try:
        result = ImageGrab.grabclipboard()
    except Exception:
        # Linux without a clipboard manager (xclip / wl-paste) raises;
        # ImageGrab also raises on some wayland setups. Treat as empty.
        return None

    if result is None:
        return None

    if isinstance(result, list):
        return _first_supported_path(result)

    # Bitmap data — save as PNG.
    return _save_bitmap(result, temp_dir)


def _first_supported_path(paths: list) -> Optional[Path]:
    """Return the first entry in ``paths`` that points at a supported image."""
    for raw in paths:
        if not isinstance(raw, str):
            continue
        try:
            path = Path(raw)
        except (OSError, TypeError, ValueError):
            continue
        if path.suffix.lower() not in SUPPORTED_IMAGE_EXTS:
            continue
        try:
            if path.exists():
                return path
        except OSError:
            continue
    return None


def _save_bitmap(image, temp_dir) -> Optional[Path]:
    """Persist a PIL Image to a fresh temp file and return its path."""
    out_dir = Path(temp_dir) if temp_dir else Path.home() / ".videokidnapper_temp"
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None

    fd, temp_path = tempfile.mkstemp(
        suffix=".png", prefix="vk_clip_", dir=str(out_dir),
    )
    os.close(fd)
    try:
        image.save(temp_path, "PNG")
    except Exception:
        # Clean up the orphan file so we don't leak .tmp droppings.
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        return None
    return Path(temp_path)
