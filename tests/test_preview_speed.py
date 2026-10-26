# SPDX-FileCopyrightText: 2026 AES256Afro <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""The preview draws less, and still draws the same thing.

Every redraw used to composite captions and stickers onto the full-size
frame and shrink the result on the window's thread: 18-40 ms per
keystroke in a caption at 1080p/4K, and more than a frame's time per
frame while playing 4K. Now the shrunk picture is kept for redraws of
the same frame, captions are drawn as patches, and playback decodes
frames near the size they are shown at. These tests pin that the
shortcuts are taken and that what ends up on screen did not move.
"""

import threading
import time

import pytest

ctk = pytest.importorskip("customtkinter")
Image = pytest.importorskip("PIL.Image")
np = pytest.importorskip("numpy")


@pytest.fixture(scope="module")
def root():
    try:
        r = ctk.CTk()
    except Exception as exc:  # noqa: BLE001 - headless CI
        pytest.skip(f"no usable display: {type(exc).__name__}")
    r.withdraw()
    yield r
    r.destroy()


@pytest.fixture
def player(root, monkeypatch):
    from videokidnapper.ui import video_player as vp

    shown = []
    real_photo = vp.ImageTk.PhotoImage
    monkeypatch.setattr(vp.ImageTk, "PhotoImage",
                        lambda img: (shown.append(img.convert("RGB")), real_photo(img))[1])
    p = vp.VideoPlayer(root)
    # A withdrawn window's widgets report 1 x 1.
    p.canvas.winfo_width = lambda: 1100
    p.canvas.winfo_height = lambda: 620
    p.video_path = "fake.mp4"
    p.duration = 10.0
    options, layers, images = {}, [], []
    p.set_export_options_provider(lambda: options)
    p.set_text_layers_provider(lambda: layers)
    p.set_image_layers_provider(lambda: images)
    p.options, p.layers, p.images, p.shown = options, layers, images, shown
    yield p
    p._playing, p._av_player = False, None
    p.destroy()


CAPTION = {"text": "A caption with a box\nand a second line", "fontsize": 64,
           "box": True, "borderw": 3, "shadowx": 4, "shadowy": 4,
           "fontcolor": "#FFCC00", "start": 0, "end": 99,
           "position": "(w-tw)/2:h-th-20"}


def _frame(w=1920, h=1080):
    return Image.linear_gradient("L").resize((w, h)).convert("RGB")


def test_redrawing_the_same_frame_reuses_the_shrunk_picture(player, monkeypatch):
    calls = []
    real = player._compose_base
    monkeypatch.setattr(player, "_compose_base",
                        lambda *a: (calls.append(1), real(*a))[1])
    frame = _frame()
    player.layers.append(dict(CAPTION))
    player._render_frame(frame, 1.0)
    player.layers[0]["text"] = "edited"          # a keystroke
    player._render_frame(frame, 1.0)
    assert len(calls) == 1

    player.set_color_provider(lambda: (0.2, 1.0, 1.0, 1.0))
    player._render_frame(frame, 1.0)             # a new grade
    player.options["aspect_preset"] = "9:16"
    player._render_frame(frame, 1.0)             # a new frame shape
    player._render_frame(_frame(), 1.0)          # a new frame
    assert len(calls) == 4


@pytest.mark.parametrize("options", [{}, {"aspect_preset": "9:16"}, {"rotate": 90}])
def test_captions_land_where_the_full_size_drawing_puts_them(player, options):
    """Drawing a caption as a patch and shrinking it must put the same
    ink in the same place as drawing it on the whole frame and shrinking
    that, which is what the export comparison tests check."""
    from videokidnapper.ui.video_player import _fit

    frame = Image.new("RGB", (1920, 1080))
    player.options.update(options)
    player.layers.append(dict(CAPTION))
    player._render_frame(frame, 1.0)
    got = np.asarray(player.shown[-1].convert("L"), float)

    geom = player._geometry
    if geom.is_subrect:
        whole = frame.copy()
        region = player._apply_text_overlay(geom.crop_source(frame), 1.0)
        whole.paste(region, geom.offset)
    else:
        whole = player._apply_text_overlay(geom.render(frame), 1.0)
    want = np.asarray(_fit(whole, player.shown[-1].size).convert("L"), float)

    def centroid(a):
        ys, xs = np.nonzero(a > 128)
        return xs.mean(), ys.mean()

    assert got.shape == want.shape
    assert np.allclose(centroid(got), centroid(want), atol=0.25)
    assert np.abs(got - want).mean() < 0.5


@pytest.mark.parametrize("options", [
    {}, {"rotate": 90}, {"aspect_preset": "9:16"},
    {"aspect_preset": "9:16", "aspect_fill_mode": "blur"},
])
def test_a_smaller_playback_frame_lays_out_like_the_full_one(player, tmp_path, options):
    """Playback decodes 4K at about the canvas size. Captions, stickers,
    clicks and drags must still use the video's own pixel space."""
    sticker = tmp_path / "s.png"
    Image.new("RGBA", (200, 200), (255, 0, 0, 255)).save(sticker)
    player.options.update(options)
    player.layers.append(dict(CAPTION))
    player.images.append({"path": str(sticker), "start": 0, "end": 99, "scale": 1.0})

    player._render_frame(_frame(3840, 2160), 1.0)
    paused = (player._layout_size, player._layout_offset, player._last_frame_rect[4:],
              player._text_bboxes, player._image_bboxes)
    size = player._playback_frame_size()
    # Far smaller than 4K. (Blur fill shows the whole source inside a
    # taller frame, so it is decoded somewhat wider than the canvas.)
    assert size is not None and size[0] <= 1920 // 1.5 and size[1] <= 620
    assert size[0] % 2 == 0 and size[1] % 2 == 0

    player._playing, player._av_player = True, object()
    player._av_render_frame(_frame(*size), 1.5)
    playing = (player._layout_size, player._layout_offset, player._last_frame_rect[4:],
               player._text_bboxes, player._image_bboxes)
    assert playing == paused
    # And the picture fills the same part of the canvas.
    assert abs(player.shown[-1].width - player.shown[-2].width) <= 2
    assert abs(player.shown[-1].height - player.shown[-2].height) <= 2


def test_small_videos_play_at_full_size(player):
    player._render_frame(_frame(640, 360), 0.0)
    assert player._playback_frame_size() is None


@pytest.mark.parametrize("options", [
    {"aspect_preset": "9:16"}, {"aspect_preset": "4:5", "aspect_fill_mode": "blur"},
    {"rotate": 90}, {"aspect_preset": "1:1", "rotate": 270},
    {"crop": {"x": 100, "y": 50, "w": 800, "h": 600}, "rotate": 180},
])
def test_geometry_renders_a_shrunk_frame_at_its_own_scale(options):
    from videokidnapper.core.frame_geometry import export_geometry

    g = export_geometry({"width": 1920, "height": 1080}, options)
    small = Image.new("RGB", (480, 270))
    w, h = g.render(small).size
    assert abs(w - g.size[0] / 4) <= 1 and abs(h - g.size[1] / 4) <= 1


def test_animated_stickers_are_decoded_off_the_window_thread(player, tmp_path, monkeypatch):
    """A long GIF took ~0.2 s to decode on the window's thread the first
    time it was previewed. Its first frame shows until it is ready."""
    from videokidnapper.utils import animated_media

    gif = tmp_path / "a.gif"
    frames = [Image.new("RGB", (40, 40), c) for c in ((255, 0, 0), (0, 0, 255))]
    frames[0].save(gif, save_all=True, append_images=frames[1:], duration=500, loop=0)
    decoded_on = []
    real = animated_media.load_animation_frames

    def spy(path):
        decoded_on.append(threading.current_thread())
        return real(path)
    monkeypatch.setattr(animated_media, "load_animation_frames", spy)
    from videokidnapper.ui import video_player as vp
    frame = Image.new("RGB", (1920, 1080))
    monkeypatch.setattr(vp, "get_frame_at", lambda *_a, **_k: frame)
    player.images.append({"path": str(gif), "start": 0, "end": 99, "scale": 1.0,
                          "position": "top_left"})

    player.show_frame(0.75)                           # frame 2 is blue
    first = player.shown[-1].getpixel((15, 15))
    assert first[0] > 200 and first[2] < 50           # still the first frame
    end = time.monotonic() + 5
    while time.monotonic() < end and player.shown[-1].getpixel((15, 15))[2] < 200:
        player.update()
        time.sleep(0.01)
    assert player.shown[-1].getpixel((15, 15))[2] > 200
    assert decoded_on and threading.main_thread() not in decoded_on
