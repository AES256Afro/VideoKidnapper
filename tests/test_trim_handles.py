# SPDX-FileCopyrightText: 2026 AES256Afro <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Trimming: handles you can grab, a selection you can draw, and words for it.

The in/out edges were 2 px lines with a 6 px grab zone, sitting on the very
first and last pixel of the timeline until moved, so they were hard to see
and harder to grab. Nothing showed what would be cut, and the buttons said
"Mark in" / "Mark out".
"""

import types

import pytest
from PIL import Image

from videokidnapper.ui.studio.timeline import (
    EDGE_GRAB_PX, HANDLE_W, clip_grab_mode, drag_selection, fade_outside,
    handle_at, render_filmstrip, render_waveform,
)
from videokidnapper.ui.trim_tab import clip_time, selection_summary

E = types.SimpleNamespace


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

def test_handles_are_tabs_inside_the_selection_on_the_media_lanes():
    # Whole clip selected: the edges sit on the timeline's first and last
    # pixel, and the tabs reach inward from there.
    assert handle_at(112 + HANDLE_W - 1, "video", 112, 900) == "in"
    assert handle_at(900 - HANDLE_W + 1, "audio", 112, 900) == "out"
    assert handle_at(500, "video", 112, 900) is None


def test_elsewhere_the_handle_is_the_line_itself():
    assert handle_at(309, "text", 300, 600) == "in"
    assert handle_at(591, "ranges", 300, 600) == "out"
    assert handle_at(320, "text", 300, 600) is None


def test_a_tiny_selection_picks_the_handle_on_the_side_of_the_press():
    assert handle_at(399, "video", 400, 404) == "in"
    assert handle_at(406, "video", 400, 404) == "out"


def test_a_short_clip_can_still_be_moved():
    # 9 px wide: 6 px edge zones used to cover all of it.
    assert clip_grab_mode(104.5, 100, 109) == "move"
    assert clip_grab_mode(100.5, 100, 109) == "start"
    assert clip_grab_mode(108.5, 100, 109) == "end"
    # A wide clip keeps the full edge zones.
    assert clip_grab_mode(100 + EDGE_GRAB_PX, 100, 300) == "start"
    assert clip_grab_mode(200, 100, 300) == "move"


@pytest.mark.parametrize("anchor,t,expected", [
    (2.0, 5.0, (2.0, 5.0)),
    (5.0, 2.0, (2.0, 5.0)),           # dragged leftward
    (8.0, 12.0, (8.0, 10.0)),         # stops at the end of the clip
    (-1.0, 3.0, (0.0, 3.0)),
    (4.0, 4.01, (4.0, 4.05)),         # never shorter than the minimum
    (4.0, 3.99, (3.95, 4.0)),
    (9.99, 10.0, (9.95, 10.0)),
])
def test_drag_selection(anchor, t, expected):
    assert drag_selection(anchor, t, 10.0) == pytest.approx(expected)


def test_filmstrip_lays_thumbnails_along_the_view():
    red = Image.new("RGB", (40, 30), "#FF0000")
    blue = Image.new("RGB", (40, 30), "#0000FF")
    strip = render_filmstrip([red, blue], 10.0, (0.0, 10.0), 400, 30, "#FFFFFF")
    assert strip.size == (400, 30)
    assert strip.getpixel((10, 15)) == (255, 0, 0)
    assert strip.getpixel((390, 15)) == (0, 0, 255)
    # Zoomed into the second half: only the blue thumbnail shows.
    zoomed = render_filmstrip([red, blue], 10.0, (5.0, 10.0), 400, 30, "#FFFFFF")
    assert zoomed.getpixel((5, 15)) == (0, 0, 255)


def test_waveform_draws_bars_on_the_lane_colour():
    img = render_waveform([0.0, 1.0], 10.0, (0.0, 10.0), 200, 32,
                          "#DDF2E7", "#1E7A4C")
    assert img.size == (200, 32)
    # Loud half: a bar through the middle; quiet half: a stub.
    assert img.getpixel((150, 4)) == (0x1E, 0x7A, 0x4C)
    assert img.getpixel((50, 4)) == (0xDD, 0xF2, 0xE7)
    assert render_waveform([], 10.0, (0.0, 10.0), 50, 20, "#000000", "#FFFFFF").size == (50, 20)


def test_fade_outside_keeps_the_selection_and_washes_out_the_rest():
    img = Image.new("RGB", (100, 10), (0, 0, 0))
    out = fade_outside(img, 30, 70, "#FFFFFF", amount=0.5)
    assert out.getpixel((50, 5)) == (0, 0, 0)
    assert out.getpixel((10, 5)) == (127, 127, 127) or out.getpixel((10, 5)) == (128, 128, 128)
    assert out.getpixel((90, 5)) == out.getpixel((10, 5))


def test_clip_time_and_summary_read_naturally():
    assert clip_time(0) == "0:00.0"
    assert clip_time(115.04) == "1:55.0"
    assert clip_time(3723.46) == "1:02:03.5"
    assert "whole video" in selection_summary(0.0, 155.0, 155.0)
    text = selection_summary(115.0, 127.2, 155.0)
    assert "1:55.0 – 2:07.2" in text and "12.2 s" in text
    assert "Open a video" in selection_summary(0, 0, 0)


# ---------------------------------------------------------------------------
# The timeline widget
# ---------------------------------------------------------------------------

ctk = pytest.importorskip("customtkinter", reason="needs customtkinter")


@pytest.fixture(scope="module")
def root():
    try:
        r = ctk.CTk()
    except Exception as exc:  # pragma: no cover - headless CI
        pytest.skip(f"no usable display: {type(exc).__name__}: {exc}")
    r.withdraw()
    yield r
    r.destroy()


@pytest.fixture
def timeline(root):
    from videokidnapper.ui.studio.timeline import TimelineView

    seen = {"selection": [], "seek": []}
    tl = TimelineView(
        root,
        on_selection_change=lambda s, e: seen["selection"].append((s, e)),
        on_seek=lambda t: seen["seek"].append(t),
    )
    tl.canvas.winfo_width = lambda: 1120          # lanes: x 112 to 1112
    tl.canvas.winfo_height = lambda: 230
    tl.duration = 100.0
    tl.set_selection(0.0, 100.0)
    tl.seen = seen
    yield tl
    tl.destroy()


def _y(lane):
    from videokidnapper.ui.studio.timeline import lane_top
    top, height = lane_top(lane)
    return top + height / 2


def test_the_in_handle_can_be_grabbed_at_the_very_start(timeline):
    x = timeline._t2x(0.0) + HANDLE_W / 2       # middle of the tab
    timeline._on_press(E(x=x, y=_y("video"), state=0))
    timeline._on_motion(E(x=x + 100, y=_y("video"), state=0))
    timeline._on_release(E(x=x + 100, y=_y("video")))
    # 100 px is 10 s, and the handle kept its offset from the mouse.
    assert timeline.sel_start == pytest.approx(10.0, abs=0.01)
    assert timeline.sel_end == 100.0
    assert timeline.seen["selection"][-1] == pytest.approx((10.0, 100.0), abs=0.01)


def test_dragging_across_the_ranges_lane_draws_a_selection(timeline):
    y = _y("ranges")
    timeline._on_press(E(x=timeline._t2x(60.0), y=y, state=0))
    timeline._on_motion(E(x=timeline._t2x(40.0), y=y, state=0))
    timeline._on_motion(E(x=timeline._t2x(30.0), y=y, state=0))
    assert (timeline.sel_start, timeline.sel_end) == pytest.approx((30.0, 60.0), abs=0.01)
    # The playhead follows the end being drawn, so the preview shows it.
    assert timeline.playhead == pytest.approx(30.0, abs=0.01)
    timeline._on_release(E(x=timeline._t2x(30.0), y=y))
    assert timeline.seen["selection"][-1] == pytest.approx((30.0, 60.0), abs=0.01)


def test_a_click_on_the_ranges_lane_just_moves_the_playhead(timeline):
    y = _y("ranges")
    x = timeline._t2x(25.0)
    timeline._on_press(E(x=x, y=y, state=0))
    timeline._on_motion(E(x=x + 1, y=y, state=0))      # a wobble, not a drag
    timeline._on_release(E(x=x + 1, y=y))
    assert (timeline.sel_start, timeline.sel_end) == (0.0, 100.0)
    assert timeline.seen["selection"] == []
    assert timeline.seen["seek"] == [pytest.approx(25.0, abs=0.01)]


def test_shift_drag_on_the_video_draws_a_selection(timeline):
    y = _y("video")
    timeline._on_press(E(x=timeline._t2x(20.0), y=y, state=0x1))
    timeline._on_motion(E(x=timeline._t2x(35.0), y=y, state=0x1))
    timeline._on_release(E(x=timeline._t2x(35.0), y=y))
    assert (timeline.sel_start, timeline.sel_end) == pytest.approx((20.0, 35.0), abs=0.01)


def test_a_plain_drag_on_the_video_still_scrubs(timeline):
    y = _y("video")
    timeline._on_press(E(x=timeline._t2x(50.0), y=y, state=0))
    timeline._on_motion(E(x=timeline._t2x(55.0), y=y, state=0))
    timeline._on_release(E(x=timeline._t2x(55.0), y=y))
    assert (timeline.sel_start, timeline.sel_end) == (0.0, 100.0)
    assert timeline.seen["seek"][-1] == pytest.approx(55.0, abs=0.01)


def test_hovering_a_handle_highlights_it(timeline):
    from videokidnapper.ui import theme as T

    timeline.redraw()
    x = timeline._t2x(100.0) - HANDLE_W / 2
    timeline._on_hover(E(x=x, y=_y("audio"), state=0))
    fills = {timeline.canvas.itemcget(i, "fill")
             for i in timeline.canvas.find_withtag("handle:out")
             if timeline.canvas.type(i) == "rectangle"}
    assert fills == {T.ACCENT_ACTIVE}
    timeline._on_hover(E(x=600, y=_y("audio"), state=0))
    fills = {timeline.canvas.itemcget(i, "fill")
             for i in timeline.canvas.find_withtag("handle:out")
             if timeline.canvas.type(i) == "rectangle"}
    assert fills == {T.ACCENT}


def test_media_lanes_are_one_picture_each_and_reused(timeline):
    timeline._thumb_images = [Image.new("RGB", (60, 40), "#336699")] * 8
    timeline._peaks = [0.5] * 100
    timeline.redraw()
    images = [i for i in timeline.canvas.find_all()
              if timeline.canvas.type(i) == "image"]
    assert len(images) == 2
    # Under 200 items in all; the waveform alone used to be ~500 lines.
    assert len(timeline.canvas.find_all()) < 200
    shown = dict(timeline._media_shown)
    timeline.set_clips(text=[{"start": 1.0, "end": 2.0, "label": "hi"}])
    # A caption edit doesn't rebuild the pictures.
    assert timeline._media_shown["video"][1] is shown["video"][1]
    timeline.set_selection(10.0, 20.0)
    assert timeline._media_shown["video"][1] is not shown["video"][1]


def test_right_clicking_a_clip_picks_it_and_offers_its_menu(timeline):
    asked, picked = [], []
    timeline._on_clip_menu = lambda *a: asked.append(a)
    timeline._on_clip_select = lambda kind, index: picked.append((kind, index))
    timeline.set_clips(text=[{"start": 10.0, "end": 20.0, "label": "hi"}])
    x = timeline._t2x(15.0)
    timeline._on_context(types.SimpleNamespace(x=x, y=_y("text"), x_root=500, y_root=400))
    assert picked == [("text", 0)] and timeline.selected == ("text", 0)
    assert asked == [("text", 0, 500, 400)]
    # Nothing on the text lane there: no menu.
    timeline._on_context(types.SimpleNamespace(x=timeline._t2x(60.0), y=_y("text"),
                                               x_root=0, y_root=0))
    assert len(asked) == 1


def test_an_unchanged_clip_list_is_not_redrawn(timeline, monkeypatch):
    """Sticker drags and most keystrokes resend the same clips."""
    clips = [{"start": 1.0, "end": 2.0, "label": "hi"}]
    timeline.set_clips(text=clips)
    redraws = []
    monkeypatch.setattr(timeline, "redraw", lambda: redraws.append(1))
    timeline.set_clips(text=[dict(c) for c in clips], images=[])
    assert redraws == []
    timeline.set_clips(text=[{"start": 1.0, "end": 2.0, "label": "hi!"}])
    assert redraws == [1]
