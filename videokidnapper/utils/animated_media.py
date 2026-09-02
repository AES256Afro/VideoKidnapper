# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Animated overlay (sticker) support: detection and ffmpeg preparation.

Image overlays were built for still pictures. The picker has always
offered ``.gif`` and ``.webp`` (``ui/image_layers.py``
``SUPPORTED_IMAGE_EXTS``), but the encoder fed every overlay to ffmpeg
as ``-loop 1``, which is an **image2 demuxer** option. Handing it a
``.gif`` makes ffmpeg exit with ``Option loop not found.`` before a
single frame is written — so adding an animated sticker silently
aborted the whole export.

This module supplies what the encoder needs to do it properly. The
behaviour of each path below was verified against ffmpeg 6.0 rather
than inferred:

===============  ===============  =========================
source           PIL sees frames  ffmpeg 6.0 animates it
===============  ===============  =========================
GIF              yes              yes  (``-stream_loop -1``)
APNG             yes              yes  (``-stream_loop -1``)
animated WebP    yes              **no** — "image data not
                                  found"; renders frozen
still image      n/a              n/a  (``-loop 1``)
===============  ===============  =========================

Animated WebP is therefore transcoded to a temporary GIF through
Pillow, which reads it correctly. That keeps the encoder's contract
simple: by the time a path reaches ffmpeg it is always something
ffmpeg can animate.

One filter-graph consequence belongs with this: an overlay input that
loops forever never reaches EOF, so any consumer that must buffer the
whole stream will hang. ``palettegen`` (every GIF export) is exactly
such a consumer — without ``shortest=1`` on the ``overlay`` filter a
GIF export with an animated sticker hangs indefinitely and writes a
zero-byte file. ``filters._build_image_overlay_chain`` sets it.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass


# Extensions whose animation ffmpeg can decode natively. APNG carries a
# plain ``.png`` extension, so ``.png`` is listed here and the frame
# count (not the extension) decides whether it is animated at all.
FFMPEG_ANIMATABLE_EXTS = frozenset({".gif", ".apng", ".png"})

# Animated sources Pillow can read but ffmpeg 6.x cannot; transcoded.
TRANSCODE_EXTS = frozenset({".webp"})

# Guard rails for the transcode path. A "sticker" with thousands of
# frames is either a mistake or a memory problem; refuse rather than
# hold it all in RAM.
MAX_TRANSCODE_FRAMES = 600


@dataclass(frozen=True)
class OverlayMedia:
    """What the encoder needs to know about one overlay file."""

    path: str
    is_animated: bool = False
    n_frames: int = 1
    #: True when ffmpeg must be told to loop the input rather than to
    #: hold a single frame.
    needs_stream_loop: bool = False
    #: Set when the file must be converted before ffmpeg can read its
    #: animation (animated WebP).
    needs_transcode: bool = False

    def input_args(self) -> list:
        """ffmpeg input flags to place immediately before ``-i``.

        ``-loop 1`` holds one still frame forever and is only valid for
        the image2 demuxer. ``-stream_loop -1`` restarts any input when
        it ends and works across demuxers, so it is the animated case.
        """
        if self.needs_stream_loop:
            return ["-stream_loop", "-1"]
        return ["-loop", "1"]


def probe_overlay(path) -> OverlayMedia:
    """Classify an overlay file. Never raises — unreadable files degrade
    to the still-image path, which is what the encoder did before."""
    path_str = str(path)
    ext = os.path.splitext(path_str)[1].lower()

    try:
        from PIL import Image

        with Image.open(path_str) as im:
            n_frames = int(getattr(im, "n_frames", 1) or 1)
            animated = bool(getattr(im, "is_animated", False)) and n_frames > 1
    except Exception:
        # Corrupt, missing, or a format Pillow does not know. Treat as a
        # still: ffmpeg will report its own error if the file is bad.
        return OverlayMedia(path=path_str)

    if not animated:
        return OverlayMedia(path=path_str, n_frames=n_frames)

    if ext in TRANSCODE_EXTS:
        return OverlayMedia(
            path=path_str, is_animated=True, n_frames=n_frames,
            needs_stream_loop=True, needs_transcode=True,
        )
    if ext in FFMPEG_ANIMATABLE_EXTS:
        return OverlayMedia(
            path=path_str, is_animated=True, n_frames=n_frames,
            needs_stream_loop=True,
        )
    # Animated, but an extension we have not verified with ffmpeg. Play
    # the first frame rather than risking a hang or a broken export.
    return OverlayMedia(path=path_str, n_frames=n_frames)


def transcode_to_gif(media: OverlayMedia):
    """Write an animated source ffmpeg cannot read out as a GIF.

    Returns the new path, or ``None`` when the caller should just use
    ``media.path`` unchanged. The caller owns the returned file and must
    delete it — see ``cleanup_transcode``.
    """
    if not media.needs_transcode:
        return None
    try:
        from PIL import Image, ImageSequence

        with Image.open(media.path) as im:
            duration = im.info.get("duration", 100) or 100
            frames = []
            for frame in ImageSequence.Iterator(im):
                frames.append(frame.convert("RGBA"))
                if len(frames) >= MAX_TRANSCODE_FRAMES:
                    break
            if len(frames) < 2:
                return None

        fd, out_path = tempfile.mkstemp(suffix="-vk-sticker.gif")
        os.close(fd)
        frames[0].save(
            out_path, save_all=True, append_images=frames[1:],
            duration=duration, loop=0, disposal=2,
        )
        return out_path
    except Exception:
        # Fall back to the still-image path rather than failing an export.
        return None


def cleanup_transcode(path) -> None:
    """Delete a file produced by :func:`transcode_to_gif`."""
    if not path:
        return
    try:
        os.unlink(path)
    except OSError:
        pass


def resolve_overlay_inputs(image_layers):
    """Prepare every overlay layer for ffmpeg in one pass.

    Returns ``(media_list, temp_paths)``. ``media_list[i]`` corresponds
    to ``image_layers[i]`` and carries the path ffmpeg should actually
    open (a transcoded temp file where one was needed). ``temp_paths``
    must be handed to :func:`cleanup_transcode` once the encode is done.
    """
    media_list = []
    temp_paths = []
    for layer in image_layers or []:
        path = (layer or {}).get("path")
        if not path:
            continue
        media = probe_overlay(path)
        if media.needs_transcode:
            converted = transcode_to_gif(media)
            if converted:
                temp_paths.append(converted)
                media = OverlayMedia(
                    path=converted, is_animated=True,
                    n_frames=media.n_frames, needs_stream_loop=True,
                )
            else:
                # Transcode failed — render the first frame statically.
                media = OverlayMedia(path=media.path, n_frames=media.n_frames)
        media_list.append(media)
    return media_list, temp_paths


# ---------------------------------------------------------------------------
# Preview support
# ---------------------------------------------------------------------------
#
# The export animates a sticker; the preview canvas composites one still
# per layer with Pillow, so an animated overlay used to sit on its first
# frame while the exported file moved. That is the only place the app's
# preview/export parity rule did not hold.
#
# Frames are decoded once per path and cached by the caller. The budget
# below is a memory guard, not a quality choice: a 600x600 sticker with
# 200 frames is ~288 MB of RGBA, which is not something to hold for a
# preview. Over budget, the sticker previews as its first frame — the
# old behaviour — rather than the app eating the memory.
MAX_PREVIEW_FRAME_PIXELS = 40_000_000  # ~160 MB of RGBA

#: Pillow reports 0 ms for some GIFs; browsers and ffmpeg both treat
#: very small values as 100 ms, so match that rather than dividing by 0.
DEFAULT_FRAME_MS = 100


def load_animation_frames(path):
    """Decode an animated overlay into ``(frames, durations_ms)``.

    Returns ``None`` for a still image, an unreadable file, or an
    animation too large for :data:`MAX_PREVIEW_FRAME_PIXELS` — in every
    one of those cases the caller should fall back to a single frame.
    """
    try:
        from PIL import Image, ImageSequence
    except Exception:  # pragma: no cover - Pillow is a hard dependency
        return None

    try:
        with Image.open(str(path)) as im:
            if not (getattr(im, "is_animated", False) and getattr(im, "n_frames", 1) > 1):
                return None

            width, height = im.size
            budget = width * height * int(im.n_frames)
            if budget > MAX_PREVIEW_FRAME_PIXELS:
                return None

            frames = []
            durations = []
            for frame in ImageSequence.Iterator(im):
                frames.append(frame.convert("RGBA"))
                # Per-frame duration; GIFs may vary it frame to frame.
                ms = frame.info.get("duration", DEFAULT_FRAME_MS)
                durations.append(int(ms) if ms and int(ms) > 0 else DEFAULT_FRAME_MS)
    except Exception:
        return None

    if len(frames) < 2:
        return None
    return frames, durations


def frame_index_at(durations_ms, seconds):
    """Which frame is on screen ``seconds`` into a looping animation.

    ffmpeg loops the overlay input continuously from the start of the
    encode (``-stream_loop -1``), and the per-layer ``enable=`` window
    only controls visibility — it does not restart the animation. So the
    frame is chosen from the timeline position modulo the loop length.

    How close this gets to the exported file, measured against ffmpeg
    6.0 with a 10-frame 100 ms sticker on a 15 fps export: the first
    loop runs ~0.133 s long — a one-off startup offset from
    ``-stream_loop``'s restart discontinuity — and every loop after it
    is exactly nominal (1.000 s, seven loops sampled). The preview
    therefore sits within about one sticker frame of the export and,
    importantly, does **not** drift further as the clip goes on.

    Correcting the constant offset would mean probing an encode to
    measure it, which is not worth doing for a preview. Frame-exact
    parity is not claimed here; "animates, and stays in step" is.
    """
    if not durations_ms:
        return 0
    total = sum(durations_ms)
    if total <= 0:
        return 0
    position = (max(0.0, float(seconds)) * 1000.0) % total
    elapsed = 0
    for index, duration in enumerate(durations_ms):
        elapsed += duration
        if position < elapsed:
            return index
    return len(durations_ms) - 1
