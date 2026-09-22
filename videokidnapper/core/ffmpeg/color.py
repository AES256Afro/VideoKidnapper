# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Colour handling: one standard working space for every export.

Why this module exists
----------------------
Exports used to hand ffmpeg whatever colour the source happened to be
in and let its defaults sort it out. For ordinary SDR video that worked.
For phone footage it did not: iPhones (and many Android phones) record
HDR by default, as 10-bit BT.2020 with an HLG or PQ transfer. Nothing
tone-mapped that down to normal video, so:

- MP4 exports stayed 10-bit HDR H.264. Plenty of phones, browsers and
  chat apps can't play that, and the ones that can often show it flat.
- GIFs (which have no HDR at all) and any player that ignored the HDR
  tags showed the raw HDR signal: measured at about 26 levels darker
  with a third of the colour saturation. "Darker and faded."

A few smaller leaks had the same root cause. Untagged video was
converted to RGB for GIFs with the SD (BT.601) matrix even when it was
HD, which shifts every hue. Sticker PNGs were converted into the video
with the SD matrix too. And a downscaled export left untagged could be
read by players with the SD matrix just because it came out small.

The fix is one rule: every export is decoded into a single working
space, **8-bit BT.709, limited range**, the format virtually every
player, browser and phone assumes and displays correctly. Then every
output is tagged as exactly that. HDR sources are tone-mapped into it
on the way in. The preview decodes through the same chain, so what you
see before export is what the export contains.

Tone mapping, measured
----------------------
HDR is graded with SDR reference white at 203 nits (ITU-R BT.2408). The
chain linearises with that as 1.0, so ordinary content maps back to its
SDR value unchanged. Above reference white, ``mobius`` with a 0.9
transition rolls highlights off towards a 1000-nit peak instead of
hard-clipping them. On test footage graded that way it reproduces the
SDR original to within compression noise (luma +0.2 of 255). The
recipe usually copied from the internet (``hable`` at 100 nits) comes
out 42 levels darker, a second way exports end up dark.
"""

import subprocess

from videokidnapper.core.ffmpeg._internals import _get_ffmpeg, _run_kwargs

#: The single working/output colour space. Players assume it for HD.
TARGET_MATRIX = "bt709"
TARGET_RANGE = "tv"

#: ffmpeg output flags that describe the working space. Every MP4 we
#: write carries these, so no player has to guess from the frame size.
OUTPUT_COLOR_ARGS = (
    "-pix_fmt", "yuv420p",
    "-colorspace", "bt709",
    "-color_primaries", "bt709",
    "-color_trc", "bt709",
    "-color_range", "tv",
)

# Transfers that mean "this is HDR" (ffprobe spellings).
_HDR_TRANSFERS = {"arib-std-b67": "arib-std-b67", "smpte2084": "smpte2084"}

# ffprobe colour_space → scale filter matrix name.
_MATRIX_NAMES = {
    "bt709": "bt709",
    "smpte170m": "smpte170m",
    "bt470bg": "bt470bg",
    "fcc": "fcc",
    "smpte240m": "smpte240m",
    "bt2020nc": "bt2020",
    "bt2020c": "bt2020",
}

# BT.2408: SDR reference white sits at 203 cd/m² in HDR programme.
_REFERENCE_WHITE_NITS = 203
# Peak assumed for tone mapping: 1000 cd/m², the HLG nominal display
# peak and the mastering peak of nearly all consumer HDR. Expressed in
# units of reference white, because that is what 1.0 means after the
# linearising step below.
_PEAK = round(1000 / _REFERENCE_WHITE_NITS, 3)

_filters_cache = None


def available_filters():
    """Names of the filters this ffmpeg build has. Cached per process."""
    global _filters_cache
    if _filters_cache is not None:
        return _filters_cache
    names = set()
    try:
        result = subprocess.run(
            [_get_ffmpeg(), "-hide_banner", "-filters"],
            capture_output=True, text=True, timeout=8, **_run_kwargs(),
        )
        for line in (result.stdout or "").splitlines():
            parts = line.split()
            # Rows look like " TSC zscale  V->V  Apply resizing...".
            if len(parts) >= 3 and "->" in parts[2]:
                names.add(parts[1])
    except Exception:
        pass
    _filters_cache = frozenset(names)
    return _filters_cache


def can_tonemap(filters=None):
    """True when HDR can be converted properly on this ffmpeg build."""
    filters = available_filters() if filters is None else filters
    return "zscale" in filters and "tonemap" in filters


def describe(info):
    """Work out what a source's colour really is.

    Returns ``(matrix, range, transfer, is_hdr)`` using the names the
    ffmpeg filters expect. Missing tags fall back to what players do:
    HD and larger is BT.709, smaller is BT.601; limited range unless the
    pixel format or tag says full.
    """
    info = info or {}
    pix_fmt = str(info.get("pix_fmt") or "")
    transfer = str(info.get("color_transfer") or "")
    space = str(info.get("color_space") or "")
    tagged_range = str(info.get("color_range") or "")

    is_hdr = transfer in _HDR_TRANSFERS
    if space in _MATRIX_NAMES:
        matrix = _MATRIX_NAMES[space]
    elif is_hdr:
        matrix = "bt2020"
    else:
        height = int(info.get("height") or 0)
        width = int(info.get("width") or 0)
        # Players pick the matrix for untagged video from its size.
        # Portrait phone video is tall rather than wide, so use the
        # short side's counterpart: anything 720p-class or bigger.
        matrix = "bt709" if max(width, height) >= 1280 or min(width, height) >= 720 \
            else "smpte170m"

    if tagged_range == "pc" or pix_fmt.startswith("yuvj"):
        color_range = "pc"
    else:
        color_range = "tv"
    return matrix, color_range, transfer, is_hdr


def needs_normalize(info):
    """True when frames must be converted into the working space."""
    matrix, color_range, _transfer, is_hdr = describe(info)
    return is_hdr or matrix != TARGET_MATRIX or color_range != TARGET_RANGE


def _tonemap_chain(transfer, color_range):
    zin = "full" if color_range == "pc" else "limited"
    return (
        # 1. HDR signal → linear light, with reference white = 1.0.
        f"zscale=tin={transfer}:min=2020_ncl:pin=2020:rin={zin}"
        f":t=linear:npl={_REFERENCE_WHITE_NITS},format=gbrpf32le,"
        # 2. BT.2020 → BT.709 primaries, still linear.
        "zscale=tin=linear:pin=2020:t=linear:p=709,"
        # 3. Roll highlights above reference white off towards the peak.
        f"tonemap=tonemap=mobius:param=0.9:desat=0:peak={_PEAK},"
        # 4. Back to gamma-encoded 8-bit BT.709. Every input property is
        #    spelled out: tonemap does not pass the transfer through, and
        #    a zscale that guesses its input is how you get dark video.
        "zscale=tin=linear:pin=709:t=709:m=709:r=limited,format=yuv420p"
    )


def build_normalize_filter(info, filters=None):
    """Filter that converts decoded frames into the working space.

    ``None`` when the source is already there (the common case for web
    video), so existing filter graphs stay byte-identical. HDR on an
    ffmpeg build without zscale/tonemap degrades to a plain 8-bit
    conversion rather than failing the export.
    """
    if not needs_normalize(info):
        return None
    matrix, color_range, transfer, is_hdr = describe(info)
    if is_hdr:
        if can_tonemap(filters):
            return _tonemap_chain(transfer, color_range)
        # No tone mapper: at least land in 8-bit BT.709 so the file
        # plays everywhere. The picture stays flat, as it was before.
        matrix = "bt2020"
    return (
        f"scale=in_color_matrix={matrix}:in_range={color_range}"
        f":out_color_matrix={TARGET_MATRIX}:out_range={TARGET_RANGE},"
        "format=yuv420p"
    )


def rgb_filter(pix_fmt="rgb24"):
    """Convert working-space frames to RGB with the right matrix.

    Left to itself, ffmpeg converts untagged YUV to RGB with the SD
    matrix. That is what shifted GIF colours from HD sources, and what
    this pins down. ``pix_fmt`` is ``bgra`` for palettegen/paletteuse.
    """
    return (
        f"scale=in_color_matrix={TARGET_MATRIX}:in_range={TARGET_RANGE},"
        f"format={pix_fmt}"
    )


#: Label frames as the working space without touching a pixel. Put
#: before a step where ffmpeg converts to RGB on its own (the GIF
#: palette filters): it then converts with the right matrix, and keeps
#: doing the resize and the conversion in one high-quality pass. A
#: separate explicit conversion splits that pass and measured slightly
#: worse at small GIF sizes.
TAG_WORKING_FILTER = (
    "setparams=colorspace=bt709:color_primaries=bt709:color_trc=bt709:range=tv"
)


def rgba_to_working_filter():
    """Convert an RGBA overlay (sticker) into the working space.

    The overlay filter would otherwise do this conversion with the SD
    matrix, tinting stickers relative to how they look in the preview.
    """
    return (
        f"scale=out_color_matrix={TARGET_MATRIX}:out_range={TARGET_RANGE},"
        "format=yuva420p"
    )


def preview_filter(info, filters=None):
    """Filter chain that decodes a frame for display: working space → RGB.

    Same normalisation as the export, so the preview shows what the
    export will contain.
    """
    parts = []
    norm = build_normalize_filter(info, filters)
    if norm:
        parts.append(norm)
    parts.append(rgb_filter("rgb24"))
    return ",".join(parts)
