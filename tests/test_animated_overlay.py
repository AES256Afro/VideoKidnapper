# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Animated sticker overlays (GIF / APNG / animated WebP).

`ui/image_layers.py` has always offered `.gif` and `.webp` in the
overlay file picker, but the encoder fed every overlay to ffmpeg with
`-loop 1` — an **image2 demuxer** option. Given a `.gif`, ffmpeg exits
with `Option loop not found.` before writing a frame, so picking an
animated sticker aborted the entire export with no usable message.

These tests pin the fix:

* the right loop flag is chosen per source,
* animated WebP (which ffmpeg 6.x cannot decode) takes a transcode path,
* `overlay=…:shortest=1` is emitted — without it a GIF export hangs
  forever, because `palettegen` buffers the whole stream and an
  infinitely-looping overlay input never reaches EOF,
* and, when ffmpeg is present, that a sticker actually moves in the
  rendered output while a still image does not.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

from videokidnapper.core.ffmpeg.filters import _build_image_overlay_chain
from videokidnapper.utils.animated_media import (
    probe_overlay,
    resolve_overlay_inputs,
)


ffmpeg_missing = shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None
skip_if_no_ffmpeg = pytest.mark.skipif(
    ffmpeg_missing, reason="ffmpeg / ffprobe not on PATH",
)

PIL = pytest.importorskip("PIL", reason="Pillow required for sticker fixtures")


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------

def _frames(n=8, size=(60, 60)):
    """`n` RGBA frames with a circle that moves left to right."""
    from PIL import Image, ImageDraw

    out = []
    for i in range(n):
        im = Image.new("RGBA", size, (0, 0, 0, 0))
        ImageDraw.Draw(im).ellipse(
            [4 + i * 3, 4, 34 + i * 3, 34], fill=(255, 60, 60, 255),
        )
        out.append(im)
    return out


@pytest.fixture
def stickers(tmp_path):
    """One of each overlay kind, in a temp dir."""
    from PIL import Image, ImageDraw

    frames = _frames()
    paths = {}

    gif = tmp_path / "sticker.gif"
    frames[0].save(gif, save_all=True, append_images=frames[1:],
                   duration=100, loop=0, disposal=2)
    paths["gif"] = gif

    apng = tmp_path / "sticker_anim.png"
    frames[0].save(apng, save_all=True, append_images=frames[1:],
                   duration=100, loop=0)
    paths["apng"] = apng

    webp = tmp_path / "sticker.webp"
    frames[0].save(webp, save_all=True, append_images=frames[1:],
                   duration=100, loop=0)
    paths["webp"] = webp

    still = tmp_path / "still.png"
    im = Image.new("RGBA", (60, 60), (0, 0, 0, 0))
    ImageDraw.Draw(im).ellipse([4, 4, 34, 34], fill=(60, 120, 255, 255))
    im.save(still)
    paths["png"] = still

    return paths


# --------------------------------------------------------------------------
# Detection
# --------------------------------------------------------------------------

def test_still_image_uses_loop_flag(stickers):
    media = probe_overlay(stickers["png"])
    assert media.is_animated is False
    assert media.input_args() == ["-loop", "1"]


@pytest.mark.parametrize("kind", ["gif", "apng"])
def test_ffmpeg_readable_animations_use_stream_loop(stickers, kind):
    """`-loop 1` is image2-only and makes ffmpeg abort on these."""
    media = probe_overlay(stickers[kind])
    assert media.is_animated is True
    assert media.n_frames > 1
    assert media.input_args() == ["-stream_loop", "-1"]
    assert media.needs_transcode is False


def test_animated_webp_is_flagged_for_transcode(stickers):
    """ffmpeg 6.x reports "image data not found" for animated WebP and
    renders it frozen, so it must be converted rather than passed through."""
    media = probe_overlay(stickers["webp"])
    assert media.is_animated is True
    assert media.needs_transcode is True


def test_unreadable_file_degrades_to_still(tmp_path):
    """A corrupt or missing overlay must not raise — the encoder should
    still build a command and let ffmpeg report the real problem."""
    bogus = tmp_path / "not-an-image.gif"
    bogus.write_bytes(b"definitely not a gif")
    media = probe_overlay(bogus)
    assert media.is_animated is False
    assert media.input_args() == ["-loop", "1"]

    missing = probe_overlay(tmp_path / "nope.png")
    assert missing.is_animated is False


# --------------------------------------------------------------------------
# Input resolution + transcode lifecycle
# --------------------------------------------------------------------------

def test_resolve_transcodes_webp_and_reports_temp(stickers):
    layers = [{"path": str(stickers["webp"])}]
    media_list, temps = resolve_overlay_inputs(layers)

    assert len(media_list) == 1
    assert len(temps) == 1, "the transcoded file must be reported for cleanup"
    converted = media_list[0]
    assert converted.path == temps[0]
    assert converted.path.endswith(".gif")
    assert converted.input_args() == ["-stream_loop", "-1"]
    assert Path(converted.path).exists()

    from videokidnapper.utils.animated_media import cleanup_transcode
    cleanup_transcode(temps[0])
    assert not Path(temps[0]).exists()


def test_resolve_leaves_other_kinds_untouched(stickers):
    layers = [{"path": str(stickers["gif"])}, {"path": str(stickers["png"])}]
    media_list, temps = resolve_overlay_inputs(layers)
    assert temps == [], "only animated WebP needs a temp file"
    assert [m.path for m in media_list] == [
        str(stickers["gif"]), str(stickers["png"]),
    ]


def test_resolve_skips_layers_without_a_path():
    media_list, temps = resolve_overlay_inputs(
        [{"path": ""}, {}, None],
    )
    assert media_list == [] and temps == []


# --------------------------------------------------------------------------
# Filter graph
# --------------------------------------------------------------------------

def test_overlay_sets_shortest_to_avoid_a_hung_gif_export():
    """Regression guard. Overlay inputs loop forever, so palettegen —
    which must buffer the whole stream — never sees EOF without this.
    Symptom was a GIF export that hung and wrote a zero-byte file."""
    chain, _label, _inputs = _build_image_overlay_chain(
        [{"path": "/tmp/s.gif", "position": "top_left", "x": 10, "y": 10}],
        base_label="vbase", video_dur=3.0,
    )
    assert "shortest=1" in chain


def test_overlay_chain_still_carries_position_and_enable():
    chain, label, inputs = _build_image_overlay_chain(
        [{"path": "/tmp/s.gif", "position": "top_left", "x": 10, "y": 10,
          "start": 0.5, "end": 2.0}],
        base_label="vbase", video_dur=3.0,
    )
    assert "overlay=x=10:y=10" in chain
    assert "enable='between(t\\,0.500\\,2.000)'" in chain
    assert label == "v_ov0"
    assert inputs == ["/tmp/s.gif"]


# --------------------------------------------------------------------------
# End-to-end (needs ffmpeg)
# --------------------------------------------------------------------------

def _still_source(path: Path, seconds=2):
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
         "-i", f"color=c=navy:s=320x240:r=15:d={seconds}",
         "-pix_fmt", "yuv420p", str(path)],
        check=True, capture_output=True,
    )


# Exact pixel equality is the wrong test here: x264 is lossy, so even a
# perfectly static frame differs slightly from its neighbours. Measured
# on the fixtures in this file (summed RGB mean delta vs. frame 0):
#
#     animated sticker   up to 5.98
#     still overlay      up to 0.03
#
# Two orders of magnitude apart, so 0.5 sits safely between them without
# being tuned to either.
MOTION_THRESHOLD = 0.5


def _motion_score(video: Path, tmp_path: Path):
    """Largest visual change between the first frame and any later one.

    Above MOTION_THRESHOLD means something in the picture actually moved;
    below it is codec noise on an otherwise static image.
    """
    from PIL import Image, ImageChops, ImageStat

    outdir = tmp_path / f"fr_{video.stem}"
    outdir.mkdir(exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(video),
         str(outdir / "f_%03d.png")],
        check=True, capture_output=True,
    )
    frames = sorted(outdir.glob("f_*.png"))
    assert len(frames) > 4, "expected several frames to compare"
    first = Image.open(frames[0]).convert("RGB")
    worst = 0.0
    for f in frames[1:]:
        diff = ImageChops.difference(first, Image.open(f).convert("RGB"))
        worst = max(worst, sum(ImageStat.Stat(diff).mean))
    return worst


@skip_if_no_ffmpeg
@pytest.mark.parametrize("kind", ["gif", "apng", "webp"])
def test_animated_sticker_actually_moves_in_export(stickers, tmp_path, kind):
    from videokidnapper.core.ffmpeg.encode import trim_to_video

    src = tmp_path / "src.mp4"
    _still_source(src)
    out = tmp_path / f"out_{kind}.mp4"

    result = trim_to_video(
        str(src), 0, 1.5, "Medium", str(out),
        image_layers=[{
            "path": str(stickers[kind]), "position": "top_left",
            "scale": 1.0, "opacity": 1.0, "start": 0, "end": 5,
            "x": 10, "y": 10,
        }],
    )
    assert result, f"{kind} sticker export failed outright"
    assert out.exists() and out.stat().st_size > 0
    # Source is a flat colour, so any inter-frame change is the sticker.
    assert _motion_score(out, tmp_path) > MOTION_THRESHOLD, \
        f"{kind} sticker rendered frozen"


@skip_if_no_ffmpeg
def test_still_overlay_does_not_animate(stickers, tmp_path):
    """Control for the test above: proves the check measures the sticker,
    not codec noise."""
    from videokidnapper.core.ffmpeg.encode import trim_to_video

    src = tmp_path / "src2.mp4"
    _still_source(src)
    out = tmp_path / "out_still.mp4"
    trim_to_video(
        str(src), 0, 1.5, "Medium", str(out),
        image_layers=[{
            "path": str(stickers["png"]), "position": "top_left",
            "scale": 1.0, "opacity": 1.0, "start": 0, "end": 5,
            "x": 10, "y": 10,
        }],
    )
    assert _motion_score(out, tmp_path) < MOTION_THRESHOLD, \
        "a still overlay must not move"


@skip_if_no_ffmpeg
def test_animated_sticker_on_gif_output(stickers, tmp_path):
    """The 'GIFs on GIFs' path — and the one that hung before shortest=1."""
    from videokidnapper.core.ffmpeg.encode import trim_to_gif

    src = tmp_path / "src3.mp4"
    _still_source(src)
    out = tmp_path / "out.gif"

    result = trim_to_gif(
        str(src), 0, 1.0, "Medium", str(out),
        image_layers=[{
            "path": str(stickers["gif"]), "position": "top_left",
            "scale": 1.0, "opacity": 1.0, "start": 0, "end": 5,
            "x": 10, "y": 10,
        }],
    )
    assert result, "GIF export with an animated sticker failed"
    assert out.exists() and out.stat().st_size > 0, "zero-byte GIF = the hang"
    assert _motion_score(out, tmp_path) > MOTION_THRESHOLD, \
        "sticker frozen in GIF output"
