# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""The preview lays captions out in the frame the export produces.

The export draws captions after the aspect preset, crop, blur fill and
rotation have reshaped the frame. The preview now renders that same
frame (see ``core.frame_geometry``), so what it shows, where a drag
lands, and how a caption wraps all match the exported file.
"""

import pytest

ctk = pytest.importorskip("customtkinter")
Image = pytest.importorskip("PIL.Image")

LONG = "this caption is far too long to fit across a vertical frame"


@pytest.fixture(scope="module")
def root():
    try:
        r = ctk.CTk()
    except Exception as exc:  # noqa: BLE001 - headless CI
        pytest.skip(f"no usable display: {type(exc).__name__}")
    r.geometry("1000x700")
    yield r
    r.destroy()


@pytest.fixture
def player(root, monkeypatch):
    from videokidnapper.ui import video_player as vp

    frame = Image.new("RGB", (1920, 1080), (0, 0, 0))
    monkeypatch.setattr(vp, "get_frame_at", lambda *_a, **_k: frame)
    p = vp.VideoPlayer(root)
    p.pack(fill="both", expand=True)
    root.update()
    p.video_path = "fake.mp4"
    p.duration = 10.0
    options = {}
    layers = []
    p.set_export_options_provider(lambda: options)
    p.set_text_layers_provider(lambda: layers)
    p.options, p.layers = options, layers
    yield p
    p.destroy()


def _show(p):
    p.show_frame(1.0)
    return p._layout_size, p._layout_offset


def test_plain_export_lays_out_on_the_whole_frame(player):
    assert _show(player) == ((1920, 1080), (0, 0))


def test_vertical_preset_lays_out_in_the_kept_window(player):
    player.options["aspect_preset"] = "9:16"
    assert _show(player) == ((607, 1080), (656, 0))


def test_long_caption_wraps_inside_the_vertical_frame(player):
    player.options["aspect_preset"] = "9:16"
    player.layers.append({"text": LONG, "fontsize": 64, "start": 0, "end": 99,
                          "position": "(w-tw)/2:h-th-20"})
    _show(player)
    (_idx, x1, _y1, x2, _y2), = player._text_bboxes
    assert 0 < x1 and x2 < 607
    # ...and it did wrap: a single line of it is wider than the frame.
    assert x2 - x1 < 607 - 20


def test_preview_and_export_break_lines_identically(player):
    """Both sides wrap with utils.text_wrap and the same font file."""
    from PIL import ImageFont

    from videokidnapper.core.ffmpeg.filters import _assemble_video_filters
    from videokidnapper.ui.text_layers import _find_font_path
    from videokidnapper.utils.text_wrap import wrap_layer_text

    layer = {"text": LONG, "fontsize": 64, "position": "(w-tw)/2:h-th-20"}
    font = ImageFont.truetype(_find_font_path("Arial"), 64)
    preview_lines = wrap_layer_text(layer, LONG, font, 607).split("\n")
    drawtext = next(f for f in _assemble_video_filters(
        "Medium", {"width": 1920, "height": 1080}, [layer], {"aspect_preset": "9:16"})
        if f.startswith("drawtext"))
    for line in preview_lines:
        assert line in drawtext
    assert drawtext.count("\n") == len(preview_lines) - 1


def test_drag_coordinates_are_layout_pixels(player):
    player.options["aspect_preset"] = "9:16"
    _show(player)
    # A click over source pixel (756, 200) is layout pixel (100, 200).
    cx, cy = player._source_to_canvas(656 + 100, 200)
    lx, ly = player._canvas_to_layout(cx, cy)
    assert abs(lx - 100) <= 2 and abs(ly - 200) <= 2


def test_rotation_shows_the_rotated_frame(player):
    player.options["rotate"] = 90
    assert _show(player) == ((1080, 1920), (0, 0))


def test_crop_mode_shows_the_source_with_the_crop_window(player):
    player.options["rotate"] = 90   # ignored while drawing the crop
    player._crop_rect = {"x": 100, "y": 100, "w": 800, "h": 600}
    player._crop_mode = True
    assert _show(player) == ((800, 600), (100, 100))


def test_tracker_boxes_map_back_to_source(player):
    player.options["aspect_preset"] = "9:16"
    _show(player)
    assert player.layout_rect_to_source(0, 0, 50, 40) == (656, 0, 706, 40)


@pytest.mark.skipif(
    __import__("shutil").which("ffmpeg") is None, reason="ffmpeg not on PATH")
@pytest.mark.parametrize("position", ["(w-tw)/2:20", "(w-tw)/2:h-th-20"])
def test_wrapped_caption_lands_on_the_same_pixels(player, tmp_path, position):
    """Multi-line captions follow drawtext's line spacing in the preview.

    Pillow spaces lines tighter than drawtext, which put wrapped captions
    up to ~20 px lower in the preview than in the export.
    """
    import subprocess

    import numpy as np

    from videokidnapper.core.ffmpeg.encode import trim_to_video

    src = tmp_path / "black.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                    "color=black:s=1920x1080:r=24:d=1.2", "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", str(src)], check=True)
    layer = {"text": "first line of the caption\nsecond gyp line\nthird",
             "fontsize": 72, "fontcolor": "white",
             "position": position, "start": 0, "end": 99}
    player.layers.append(layer)
    preview = player._apply_text_overlay(Image.new("RGB", (1920, 1080)), 1.0)
    out = trim_to_video(str(src), 0, 1.0, "Ultra", str(tmp_path / "o.mp4"),
                        text_layers=[layer], options={"hw_encoder": "off"})
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", "0.5", "-i", str(out),
                          "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                         capture_output=True, check=True).stdout
    exported = np.frombuffer(raw, np.uint8).reshape(1080, 1920)

    def ink_box(a):
        m = a > 100
        ys, xs = m.any(1).nonzero()[0], m.any(0).nonzero()[0]
        return xs.min(), ys.min(), xs.max(), ys.max()

    assert ink_box(np.asarray(preview.convert("L"))) == ink_box(exported)


# ---------------------------------------------------------------------------
# Captions never fall off the frame, and the preview agrees on where
# ---------------------------------------------------------------------------

def _export_ink(tmp_path, layer, t=0.5):
    import subprocess

    import numpy as np

    from videokidnapper.core.ffmpeg.encode import trim_to_video

    src = tmp_path / "black.mp4"
    if not src.exists():
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                        "color=black:s=1920x1080:r=24:d=1.2", "-c:v", "libx264",
                        "-pix_fmt", "yuv420p", str(src)], check=True)
    out = trim_to_video(str(src), 0, 1.0, "Ultra", str(tmp_path / "o.mp4"),
                        text_layers=[layer], options={"hw_encoder": "off"})
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(t), "-i", str(out),
                          "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                         capture_output=True, check=True).stdout
    return _ink(np.frombuffer(raw, np.uint8).reshape(1080, 1920))


def _ink(a):
    import numpy as np
    m = np.asarray(a) > 100
    ys, xs = m.any(1).nonzero()[0], m.any(0).nonzero()[0]
    return int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())


def _inside(box, w=1920, h=1080):
    """Ink touches no edge. Text clipped by an edge reaches row/column 0
    or the last one, so a caption that fell off fails this."""
    x1, y1, x2, y2 = box
    return x1 > 0 and y1 > 0 and x2 < w - 1 and y2 < h - 1


need_ffmpeg = pytest.mark.skipif(
    __import__("shutil").which("ffmpeg") is None, reason="ffmpeg not on PATH")


@need_ffmpeg
@pytest.mark.parametrize("position", ["1850:1040", "1500:-300", "-400:500"])
def test_dragged_caption_is_kept_on_screen(player, tmp_path, position):
    layer = {"text": "edge case", "fontsize": 90, "fontcolor": "white",
             "borderw": 4, "bordercolor": "black",
             "position": position, "start": 0, "end": 99}
    exported = _export_ink(tmp_path, layer)
    assert _inside(exported), exported
    player.layers.append(layer)
    preview = player._apply_text_overlay(Image.new("RGB", (1920, 1080)), 0.5)
    px = _ink(preview.convert("L"))
    assert all(abs(a - b) <= 2 for a, b in zip(px, exported)), (px, exported)


@need_ffmpeg
def test_too_tall_caption_shrinks_to_fit(player, tmp_path):
    words = " ".join(["caption"] * 40)
    layer = {"text": words, "fontsize": 220, "fontcolor": "white",
             "position": "(w-tw)/2:h-th-20", "start": 0, "end": 99}
    exported = _export_ink(tmp_path, layer)
    assert _inside(exported), exported
    player.layers.append(layer)
    preview = player._apply_text_overlay(Image.new("RGB", (1920, 1080)), 0.5)
    assert _ink(preview.convert("L")) == exported


@need_ffmpeg
def test_motion_path_cannot_leave_the_frame(player, tmp_path):
    layer = {"text": "tracked", "fontsize": 80, "fontcolor": "white",
             "keyframes": [{"t": 0.0, "x": 100, "y": 500},
                           {"t": 1.0, "x": 4000, "y": 2500}],
             "start": 0, "end": 99}
    exported = _export_ink(tmp_path, layer, t=0.75)
    assert _inside(exported), exported
