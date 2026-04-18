# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Tests for transitions between concatenated clips."""

from videokidnapper.core.ffmpeg_backend import (
    CONCAT_TRANSITIONS, _build_xfade_filter_complex,
    _xfade_transition_name,
)


# ---------------------------------------------------------------------------
# Label → ffmpeg transition name mapping
# ---------------------------------------------------------------------------

def test_crossfade_maps_to_dissolve():
    # ffmpeg has no "crossfade" transition — the closest match is "dissolve".
    assert _xfade_transition_name("crossfade") == "dissolve"


def test_fade_to_black_and_white_keep_names():
    assert _xfade_transition_name("fade") == "fade"
    assert _xfade_transition_name("fadeblack") == "fadeblack"
    assert _xfade_transition_name("fadewhite") == "fadewhite"


def test_unknown_transition_falls_back_to_fade():
    # A corrupt settings value should still produce a valid filter, not blow up.
    assert _xfade_transition_name("magic") == "fade"


def test_cut_is_in_the_set():
    assert "cut" in CONCAT_TRANSITIONS
    assert "crossfade" in CONCAT_TRANSITIONS
    assert "fadeblack" in CONCAT_TRANSITIONS
    assert "fadewhite" in CONCAT_TRANSITIONS


# ---------------------------------------------------------------------------
# Filter-complex construction
# ---------------------------------------------------------------------------

def test_single_clip_returns_empty_filter():
    # Nothing to transition with one clip.
    fc, vm, am = _build_xfade_filter_complex(
        durations=[5.0], has_audio=True, transition="fade", duration=0.5,
    )
    assert fc == ""
    assert vm is None and am is None


def test_two_clips_with_audio_produces_v_and_a_chains():
    fc, vm, am = _build_xfade_filter_complex(
        durations=[5.0, 3.0], has_audio=True, transition="fade", duration=0.5,
    )
    # Video: one xfade at offset 4.5 (5.0 - 1*0.5)
    assert "xfade=transition=fade" in fc
    assert "offset=4.500" in fc
    assert "[vout]" in fc
    # Audio: one acrossfade
    assert "acrossfade=d=0.500" in fc
    assert "[aout]" in fc
    assert vm == "[vout]"
    assert am == "[aout]"


def test_three_clips_chain_offsets_are_cumulative():
    # Durations 4, 3, 5 with 0.5s transition:
    # transition 0→1 starts at 4 - 0.5 = 3.5
    # transition 1→2 starts at 4 + 3 - 2*0.5 = 6.0
    fc, _vm, _am = _build_xfade_filter_complex(
        durations=[4.0, 3.0, 5.0],
        has_audio=False, transition="crossfade", duration=0.5,
    )
    assert "offset=3.500" in fc
    assert "offset=6.000" in fc
    # crossfade maps to ffmpeg's dissolve
    assert "xfade=transition=dissolve" in fc


def test_no_audio_omits_acrossfade_chain():
    fc, vm, am = _build_xfade_filter_complex(
        durations=[4.0, 3.0], has_audio=False,
        transition="fadeblack", duration=0.5,
    )
    assert "acrossfade" not in fc
    assert am is None
    assert vm == "[vout]"


def test_tiny_duration_is_clamped_up():
    # duration = 0.001 should clamp to at least 0.05 so ffmpeg doesn't
    # reject the filter-graph with a "transition too short" error.
    fc, _vm, _am = _build_xfade_filter_complex(
        durations=[5.0, 5.0], has_audio=True,
        transition="fade", duration=0.001,
    )
    assert "duration=0.050" in fc


def test_offset_cannot_go_negative():
    # Clip 0 shorter than the transition → cumulative - i*t goes
    # negative; clamped to 0 so ffmpeg gets a valid command.
    fc, _vm, _am = _build_xfade_filter_complex(
        durations=[0.3, 5.0], has_audio=False,
        transition="fade", duration=0.5,
    )
    assert "offset=0.000" in fc
