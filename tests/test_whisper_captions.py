# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Tests for the Whisper auto-captions plumbing.

We don't exercise the actual transcription (requires a model file +
real audio). The value in testing is:

- pure segment → SRT-dict conversion (``segments_to_entries``)
- availability probe shape (boolean, never raises)
- unknown-model-size error surface
- a "missing dep" path that returns the right error instead of crashing

Real transcription quality is a faster-whisper concern, not ours.
"""
import types

import pytest

from videokidnapper.core import whisper_captions
from videokidnapper.core.whisper_captions import (
    MODEL_SIZES, segments_to_entries, transcribe,
)


# ---------------------------------------------------------------------------
# Availability probe
# ---------------------------------------------------------------------------

def test_is_available_is_boolean():
    # Whether the dep is installed depends on the env — just pin the shape.
    assert isinstance(whisper_captions.is_available(), bool)


# ---------------------------------------------------------------------------
# Segment → SRT-dict conversion
# ---------------------------------------------------------------------------

def _seg(start, end, text):
    """Build an object that walks like a faster-whisper Segment."""
    return types.SimpleNamespace(start=start, end=end, text=text)


def test_segments_to_entries_basic():
    out = segments_to_entries([
        _seg(0.0, 1.5, " Hello world "),
        _seg(1.5, 3.0, "Second line"),
    ])
    assert len(out) == 2
    assert out[0] == {"start": 0.0, "end": 1.5, "text": "Hello world"}
    assert out[1] == {"start": 1.5, "end": 3.0, "text": "Second line"}


def test_segments_to_entries_skips_empty_text():
    # Whisper occasionally emits empty segments for silence / padding;
    # those should NOT become text layers (they'd render as nothing
    # but clutter the panel).
    out = segments_to_entries([
        _seg(0.0, 1.0, ""),
        _seg(1.0, 2.0, "   "),
        _seg(2.0, 3.0, "real text"),
    ])
    assert out == [{"start": 2.0, "end": 3.0, "text": "real text"}]


def test_segments_to_entries_fixes_zero_duration():
    # A segment where end <= start gets expanded so the caption is
    # actually visible at export time.
    out = segments_to_entries([_seg(5.0, 5.0, "whoops")])
    assert out[0]["start"] == 5.0
    assert out[0]["end"] > 5.0


def test_segments_to_entries_applies_time_offset():
    # When captioning a trim-range starting at t=10s, Whisper's
    # internal timestamps start at 0; the caller adds the offset so
    # the resulting layers use absolute video-timeline times.
    out = segments_to_entries(
        [_seg(0.0, 2.0, "hi"), _seg(3.0, 5.0, "bye")],
        time_offset=10.0,
    )
    assert out[0]["start"] == 10.0
    assert out[0]["end"] == 12.0
    assert out[1]["start"] == 13.0
    assert out[1]["end"] == 15.0


def test_segments_to_entries_accepts_dict_like_items():
    # getattr-based reads mean plain SimpleNamespaces work, but so do
    # objects with only the three attributes. Confirm the contract.
    class Loose:
        start = 1.0
        end = 2.0
        text = "loose"
    out = segments_to_entries([Loose()])
    assert out == [{"start": 1.0, "end": 2.0, "text": "loose"}]


# ---------------------------------------------------------------------------
# transcribe()
# ---------------------------------------------------------------------------

def test_transcribe_rejects_unknown_model_size():
    with pytest.raises(ValueError, match="unknown model_size"):
        transcribe("bogus.mp4", model_size="ludicrous")


def test_transcribe_raises_when_dep_missing(monkeypatch):
    monkeypatch.setattr(
        whisper_captions, "is_available", lambda: False,
    )
    with pytest.raises(RuntimeError, match="faster-whisper is not installed"):
        transcribe("bogus.mp4", model_size="base")


def test_model_sizes_include_tiny_through_large():
    assert "tiny" in MODEL_SIZES
    assert "base" in MODEL_SIZES
    assert "small" in MODEL_SIZES
    assert "medium" in MODEL_SIZES
    assert "large" in MODEL_SIZES
