#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Turn the raw captures from capture_screenshots.py into Store images.

The Microsoft Store wants a fixed size; the guide standardises on
1920x1080. Captures come out at the app's own window size, so each one
is centred on a 1920x1080 canvas filled with the active theme's base
colour rather than stretched — a scaled-up Tk window looks blurry, and
a letterbox in the theme colour reads as intentional.

Usage:  python scripts/store_screenshots.py [--theme cream]
Reads assets/screenshots/*.png, writes assets/store/NN-name-1920x1080.png.
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SRC = ROOT / "assets" / "screenshots"
OUT = ROOT / "assets" / "store"
SIZE = (1920, 1080)

#: Store order (first is the hero shot) -> source capture.
SEQUENCE = [
    ("01-studio",   "studio_loaded.png"),
    ("02-download", "studio_link.png"),
    ("03-start",    "studio_empty.png"),
    ("04-history",  "history.png"),
    ("05-setup",    "setup.png"),
]


def main():
    from PIL import Image

    from videokidnapper.ui.theme import PALETTES

    ap = argparse.ArgumentParser()
    ap.add_argument("--theme", default="cream", choices=sorted(PALETTES))
    args = ap.parse_args()
    bg = PALETTES[args.theme]["BG_BASE"]

    OUT.mkdir(parents=True, exist_ok=True)
    written = 0
    for stem, source in SEQUENCE:
        src = SRC / source
        if not src.exists():
            print(f"  skip {stem}: {source} not captured")
            continue
        shot = Image.open(src).convert("RGB")
        if shot.width > SIZE[0] or shot.height > SIZE[1]:
            shot.thumbnail(SIZE, Image.LANCZOS)
        canvas = Image.new("RGB", SIZE, bg)
        canvas.paste(shot, ((SIZE[0] - shot.width) // 2, (SIZE[1] - shot.height) // 2))
        target = OUT / f"{stem}-1920x1080.png"
        canvas.save(target, "PNG", optimize=True)
        print(f"  {target.name}  <- {source} {shot.size}")
        written += 1
    print(f"{written} store image(s) in {OUT}")
    return 0 if written else 1


if __name__ == "__main__":
    sys.exit(main())
