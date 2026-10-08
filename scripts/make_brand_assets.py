#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Regenerate every logo, icon and Store image from the retro-stamp badge.

The badge is defined once, in code, below. Its ring text and the wordmark
are converted to outlines with fontTools (fonts vendored under
assets/branding/fonts/), so the SVG masters render the same everywhere,
including in an <img> tag that can't load web fonts. Raster files are
rendered by headless Chrome or Edge.

Two marks are produced:
  * the badge (ring text, mask, stars) for 64 px and up;
  * a ring-free mark (the mask on a solid disc) for anything smaller,
    where the ring text would be an unreadable smudge.

Local use. Needs fonttools (pip install fonttools) and Chrome or Edge;
set VK_CHROME to a browser executable to override the lookup.

    python scripts/make_brand_assets.py
"""

import math
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
BRAND = ROOT / "assets" / "branding"
FONTS = BRAND / "fonts"
MSIX = ROOT / "packaging" / "msix" / "Assets"
APP_ASSETS = ROOT / "videokidnapper" / "assets"

CREAM = "#F3E9D2"
NAVY = "#1F2A44"
ORANGE = "#E4572E"
ORANGE_LIGHT = "#F28B6B"

# The balaclava, as drawn on the Design canvas (512 box, evenodd cutouts).
MASK = (
    "M 140 420 C 128 372 120 320 120 268 C 120 152 182 88 256 88 "
    "C 330 88 392 152 392 268 C 392 320 384 372 372 420 C 330 436 182 436 140 420 Z "
    "M 150.4 243.6 a 46 26 8 1 0 91.2 12.8 a 46 26 8 1 0 -91.2 -12.8 Z "
    "M 270.4 256.4 a 46 26 -8 1 0 91.2 -12.8 a 46 26 -8 1 0 -91.2 12.8 Z "
    "M 226 334 a 30 18 0 1 0 60 0 a 30 18 0 1 0 -60 0 Z"
)
STAR = "\u2726"


# ---------------------------------------------------------------------------
# Glyph outlines
# ---------------------------------------------------------------------------

class Face:
    """One font file: glyph advances and SVG outlines."""

    def __init__(self, path):
        self.font = TTFont(path)
        self.glyphs = self.font.getGlyphSet()
        self.cmap = self.font.getBestCmap()
        self.upm = self.font["head"].unitsPerEm

    def name(self, ch):
        return self.cmap[ord(ch)]

    def advance(self, ch, size):
        # The star separator is drawn as a shape, not a glyph; give it a
        # letter's width (every glyph is that wide in a monospace face).
        name = self.name("M" if ch == STAR else ch)
        return self.font["hmtx"][name][0] * size / self.upm

    def outline(self, ch, size, transform):
        """SVG path data for ``ch`` at ``size`` px, after ``transform``.

        ``transform`` is a 2x3 affine (a, b, c, d, e, f) applied to the
        glyph in px with y pointing up from the baseline.
        """
        k = size / self.upm
        a, b, c, d, e, f = transform
        # Font units (y up) -> px (y up) -> caller's transform (y down page).
        pen = SVGPathPen(self.glyphs, ntos=lambda v: f"{v:.2f}")
        tpen = TransformPen(pen, (a * k, b * k, -c * k, -d * k, e, f))
        self.glyphs[self.name(ch)].draw(tpen)
        return pen.getCommands()


def _star_points(cx, cy, outer, inner, rot=0.0):
    pts = []
    for i in range(8):
        r = outer if i % 2 == 0 else inner
        ang = rot + i * math.pi / 4 - math.pi / 2
        pts.append(f"{cx + r * math.cos(ang):.2f},{cy + r * math.sin(ang):.2f}")
    return " ".join(pts)


def arc_text(face, text, size, radius, length, side, fill, cx=256, cy=256):
    """Text along a circle, fitted to ``length`` px, centred on the arc.

    side="top": baseline runs left to right over the top, glyphs outward.
    side="bottom": left to right under the bottom, glyph tops inward, so
    both arcs read upright (the classic stamp layout). Spacing is spread
    evenly between glyphs, like SVG's lengthAdjust="spacing". A star
    character is drawn as a four-point star the height of a capital.
    """
    adv = [face.advance(ch, size) for ch in text]
    gap = (length - sum(adv)) / (len(text) - 1)
    mid = math.pi * radius / 2  # half the semicircle
    s = mid - length / 2
    cap = face.font["OS/2"].sCapHeight * size / face.upm
    paths, stars = [], []
    for ch, w in zip(text, adv):
        centre = s + w / 2
        if side == "top":
            theta = math.pi + centre / radius
            rot = theta + math.pi / 2
        else:
            theta = math.pi - centre / radius
            rot = theta - math.pi / 2
        px, py = cx + radius * math.cos(theta), cy + radius * math.sin(theta)
        cr, sr = math.cos(rot), math.sin(rot)
        if ch == STAR:
            # Centre of a capital, measured "up" from the baseline.
            ux, uy = sr, -cr  # local up (-y) after rotation
            stars.append(_star_points(px + ux * cap / 2, py + uy * cap / 2,
                                      cap * 0.62, cap * 0.2, rot))
        elif ch != " ":
            # Glyph origin sits half an advance before its centre.
            ox, oy = px - cr * w / 2, py - sr * w / 2
            paths.append(face.outline(ch, size, (cr, sr, -sr, cr, ox, oy)))
        s += w + gap
    out = f'<path fill="{fill}" d="{" ".join(paths)}"/>'
    for pts in stars:
        out += f'<polygon fill="{ORANGE}" points="{pts}"/>'
    return out


def line_text(face, parts, size, x, baseline):
    """Straight text of (string, colour) runs; returns (svg, width)."""
    svg, pen_x = [], x
    for text, colour in parts:
        d = []
        for ch in text:
            d.append(face.outline(ch, size, (1, 0, 0, 1, pen_x, baseline)))
            pen_x += face.advance(ch, size)
        svg.append(f'<path fill="{colour}" d="{" ".join(d)}"/>')
    return "".join(svg), pen_x - x


# ---------------------------------------------------------------------------
# Marks
# ---------------------------------------------------------------------------

MONO = Face(FONTS / "SpaceMono-Bold.ttf")
SLAB = Face(FONTS / "AlfaSlabOne-Regular.ttf")


def badge_body():
    """The full badge, in a 512 box."""
    return "".join([
        f'<circle cx="256" cy="256" r="244" fill="{CREAM}" stroke="{NAVY}" stroke-width="12"/>',
        f'<circle cx="256" cy="256" r="172" fill="{NAVY}"/>',
        arc_text(MONO, "VIDEO KIDNAPPER", 44, 190, 500, "top", NAVY),
        arc_text(MONO, f"DOWNLOAD {STAR} TRIM {STAR} CAPTION {STAR} EXPORT",
                 25, 224, 560, "bottom", NAVY),
        f'<polygon fill="{ORANGE}" points="{_star_points(48, 256, 14, 4)}"/>',
        f'<polygon fill="{ORANGE}" points="{_star_points(464, 256, 14, 4)}"/>',
        f'<path fill="{CREAM}" fill-rule="evenodd" '
        f'transform="translate(256 260) scale(0.64) translate(-256 -262)" d="{MASK}"/>',
        f'<circle cx="256" cy="400" r="10" fill="{ORANGE}"/>',
    ])


def mark_body(disc=NAVY, mask=CREAM, rim=CREAM):
    """Ring-free mark for small sizes: the mask on a solid disc.

    The thin outer rim echoes the badge's ring and keeps the disc's edge
    visible on a dark taskbar, where navy alone would vanish.
    """
    rim_svg = (f'<circle cx="256" cy="256" r="250" fill="{rim}"/>'
               if rim else "")
    disc_r = 216 if rim else 250
    return (rim_svg
            + f'<circle cx="256" cy="256" r="{disc_r}" fill="{disc}"/>'
            f'<path fill="{mask}" fill-rule="evenodd" '
            f'transform="translate(256 262) scale(0.70) translate(-256 -262)" d="{MASK}"/>')


def svg_doc(body, w=512, h=512, view=None, comment=""):
    view = view or f"0 0 {w} {h}"
    note = f"<!-- {comment} -->\n" if comment else ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
            f'viewBox="{view}">\n{note}{body}\n</svg>\n')


def place(body, x, y, size):
    """A 512-box mark drawn at (x, y), ``size`` px square."""
    return f'<g transform="translate({x} {y}) scale({size / 512})">{body}</g>'


def wordmark(size, x, baseline, dark):
    first, second = (CREAM, ORANGE_LIGHT) if dark else (NAVY, ORANGE)
    return line_text(SLAB, [("Video", first), ("Kidnapper", second)], size, x, baseline)


def wordmark_width(size):
    return sum(SLAB.advance(ch, size) for ch in "VideoKidnapper")


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def find_browser():
    env = os.environ.get("VK_CHROME")
    if env:
        return env
    for cand in (
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    ):
        if Path(cand).exists():
            return cand
    for name in ("google-chrome", "chromium", "chromium-browser", "chrome", "msedge"):
        found = shutil.which(name)
        if found:
            return found
    sys.exit("No Chrome or Edge found; set VK_CHROME to a browser executable.")


BROWSER = find_browser()
TMP = Path(tempfile.mkdtemp(prefix="vk-brand-"))


def render(svg, w, h, out, background=None):
    """Rasterise an SVG document to ``out`` at exactly w x h."""
    page = TMP / "page.html"
    bg = background or "transparent"
    page.write_text(
        "<!doctype html><html><head><style>html,body{margin:0;overflow:hidden;"
        f"background:{bg}}}svg{{display:block}}</style></head><body>{svg}</body></html>",
        encoding="utf-8")
    shot = TMP / "shot.png"
    subprocess.run([
        BROWSER, "--headless=new", "--disable-gpu", "--hide-scrollbars",
        "--force-device-scale-factor=1", "--default-background-color=00000000",
        f"--window-size={w},{h}", f"--screenshot={shot}", page.as_uri(),
    ], check=True, capture_output=True)
    im = Image.open(shot)
    im.load()
    if im.size != (w, h):
        raise RuntimeError(f"rendered {im.size}, wanted {(w, h)}")
    if background:
        im = im.convert("RGB")
    out.parent.mkdir(parents=True, exist_ok=True)
    im.save(out, optimize=True)
    return im


def downsample(im, size):
    """High-quality square resize with premultiplied alpha."""
    return im.convert("RGBa").resize((size, size), Image.LANCZOS).convert("RGBA")


# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------

def main():
    badge, mark, mark_light = badge_body(), mark_body(), mark_body(CREAM, NAVY, rim=None)

    # SVG masters.
    (BRAND / "logo.svg").write_text(svg_doc(
        badge, comment="VideoKidnapper badge. Generated by scripts/make_brand_assets.py; "
                       "edit the script, not this file."), encoding="utf-8")
    (BRAND / "logo-mark.svg").write_text(svg_doc(
        mark, comment="Small-size mark (no ring text). Generated by "
                      "scripts/make_brand_assets.py."), encoding="utf-8")
    (BRAND / "logo-white.svg").write_text(svg_doc(
        mark_light, comment="Small-size mark for dark backgrounds. Generated by "
                            "scripts/make_brand_assets.py."), encoding="utf-8")

    # Big renders the square icons are cut from.
    big_badge = render(svg_doc(badge, 1024, 1024, "0 0 512 512"), 1024, 1024,
                       BRAND / "logo-1024.png")
    big_mark = render(svg_doc(mark, 1024, 1024, "0 0 512 512"), 1024, 1024,
                      TMP / "mark-1024.png")

    def icon(size):
        """The badge from 64 px up, the ring-free mark below."""
        return downsample(big_badge if size >= 64 else big_mark, size)

    icon(512).save(BRAND / "logo-512.png", optimize=True)
    downsample(big_mark, 64).save(BRAND / "favicon-64.png", optimize=True)

    # Lockups: badge + wordmark, 440 tall. The transparent ones run edge
    # to edge; the one on its own navy card gets a margin all round.
    h, gap, ws = 440, 56, 196
    for name, dark, bg in (("logo-lockup.png", True, None),
                           ("logo-lockup-onlight.png", False, None),
                           ("logo-lockup-dark.png", True, NAVY)):
        pad = 40 if bg else 0
        size = h - 2 * pad
        scale = size / h
        word = ws * scale
        lock_w = int(2 * pad + size + gap * scale + wordmark_width(word) + 24 * scale)
        text, _w = wordmark(word, pad + size + gap * scale, pad + 288 * scale, dark)
        body = place(badge, pad, pad, size) + text
        render(svg_doc(body, lock_w, h), lock_w, h, BRAND / name, background=bg)

    # Social card, Store box art and posters: navy, badge over wordmark.
    def card(w, h, badge_size, badge_y, word_size, word_base, out):
        text, tw = wordmark(word_size, 0, word_base, True)
        body = (f'<rect width="{w}" height="{h}" fill="{NAVY}"/>'
                + place(badge, (w - badge_size) / 2, badge_y, badge_size)
                + f'<g transform="translate({(w - tw) / 2:.1f} 0)">{text}</g>')
        render(svg_doc(body, w, h), w, h, out, background=NAVY)

    card(1280, 720, 420, 70, 76, 620, BRAND / "logo-card-1280x720.png")
    for s in (1080, 2160):
        k = s / 1080
        card(s, s, int(620 * k), int(110 * k), int(96 * k), int(920 * k),
             BRAND / f"store-boxart-{s}x{s}.png")
    for w, hh in ((720, 1080), (1440, 2160)):
        k = w / 720
        card(w, hh, int(520 * k), int(210 * k), int(66 * k), int(880 * k),
             BRAND / f"store-poster-{w}x{hh}.png")

    # Store 16:9 "super hero" art: shown at the top of the Store page, and
    # the Store forbids the product name in it, so it uses the ring-free
    # mark (the badge spells the name) beside the Edit screenshot.
    source = ROOT / "assets" / "screenshots" / "studio_loaded.png"
    if source.exists():
        # Crop off the title bar and app header, which spell the name.
        full = Image.open(source)
        shot = TMP / "hero-shot.png"
        full.crop((0, 88, full.width, full.height)).save(shot)
        sw, sh = Image.open(shot).size
        for w, hh in ((1920, 1080), (3840, 2160)):
            k = w / 1920
            img_w = 1180 * k
            img_h = img_w * sh / sw
            ix, iy = 640 * k, (hh - img_h) / 2
            body = (f'<defs><clipPath id="r"><rect x="{ix}" y="{iy}" width="{img_w}" '
                    f'height="{img_h}" rx="{18 * k}"/></clipPath>'
                    f'<filter id="s" x="-10%" y="-10%" width="120%" height="130%">'
                    f'<feDropShadow dx="0" dy="{18 * k}" stdDeviation="{24 * k}" '
                    f'flood-color="#000" flood-opacity="0.45"/></filter></defs>'
                    f'<rect width="{w}" height="{hh}" fill="{NAVY}"/>'
                    + place(mark, 150 * k, (hh - 400 * k) / 2, 400 * k)
                    + f'<rect x="{ix}" y="{iy}" width="{img_w}" height="{img_h}" rx="{18 * k}" '
                    f'fill="{NAVY}" filter="url(#s)"/>'
                    f'<image href="{shot.as_uri()}" x="{ix}" y="{iy}" width="{img_w}" '
                    f'height="{img_h}" clip-path="url(#r)" preserveAspectRatio="xMidYMid slice"/>')
            render(svg_doc(body, w, hh), w, hh, BRAND / f"store-hero-{w}x{hh}.png",
                   background=NAVY)

    # Store tile overrides (opaque, on navy).
    for s in (300, 150, 71):
        inner = int(s * 0.84)
        body = (f'<rect width="{s}" height="{s}" fill="{NAVY}"/>'
                + place(badge if s >= 100 else mark, (s - inner) / 2, (s - inner) / 2, inner))
        render(svg_doc(body, s, s), s, s, BRAND / f"store-tile-{s}x{s}.png", background=NAVY)

    # MSIX tiles (transparent). Square tiles get breathing room; the
    # Square44 family is the taskbar / Start icon and fills its box.
    def padded(size, frac, src=None):
        canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        inner = round(size * frac)
        art = downsample(src if src is not None else (big_badge if inner >= 64 else big_mark), inner)
        canvas.alpha_composite(art, ((size - inner) // 2, (size - inner) // 2))
        return canvas

    padded(150, 0.80).save(MSIX / "Square150x150Logo.png", optimize=True)
    padded(310, 0.80).save(MSIX / "Square310x310Logo.png", optimize=True)
    icon(44).save(MSIX / "Square44x44Logo.png", optimize=True)
    for t in (16, 24, 32, 48, 256):
        img = icon(t)
        img.save(MSIX / f"Square44x44Logo.targetsize-{t}.png", optimize=True)
        img.save(MSIX / f"Square44x44Logo.targetsize-{t}_altform-unplated.png", optimize=True)
    icon(50).save(MSIX / "StoreLogo.png", optimize=True)
    wide = Image.new("RGBA", (310, 150), (0, 0, 0, 0))
    wide.alpha_composite(downsample(big_badge, 124), ((310 - 124) // 2, 13))
    wide.save(MSIX / "Wide310x150Logo.png", optimize=True)

    # App icons.
    icon(256).save(APP_ASSETS / "icon.png", optimize=True)
    downsample(big_mark, 64).save(APP_ASSETS / "mark.png", optimize=True)
    ico_sizes = [16, 24, 32, 48, 64, 128, 256]
    base = icon(256)
    base.save(APP_ASSETS / "icon.ico", sizes=[(s, s) for s in ico_sizes],
              append_images=[icon(s) for s in ico_sizes if s != 256])
    icns_sizes = [16, 32, 64, 128, 256, 512]
    icon(1024).save(APP_ASSETS / "icon.icns",
                    append_images=[icon(s) for s in icns_sizes])

    shutil.rmtree(TMP, ignore_errors=True)
    print("Brand assets regenerated.")


if __name__ == "__main__":
    main()
