# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
from videokidnapper.utils.srt_parser import parse_srt, srt_to_text_layers


SAMPLE = """1
00:00:00,500 --> 00:00:02,000
Hello world

2
00:00:02,100 --> 00:00:04,000
Line two
continues here

3
00:00:05,000 --> 00:00:06,500
Goodbye
"""


def test_parse_counts_entries():
    entries = parse_srt(SAMPLE)
    assert len(entries) == 3


def test_parse_timestamps():
    entries = parse_srt(SAMPLE)
    assert entries[0]["start"] == 0.5
    assert entries[0]["end"]   == 2.0
    assert entries[2]["start"] == 5.0


def test_parse_multiline_text():
    entries = parse_srt(SAMPLE)
    assert "Line two\ncontinues here" in entries[1]["text"]


def test_parse_vtt_dot_separator():
    vtt = """00:00:01.000 --> 00:00:03.000
Caption"""
    entries = parse_srt(vtt)
    assert entries == [{"start": 1.0, "end": 3.0, "text": "Caption"}]


def test_srt_to_layers_schema():
    entries = parse_srt(SAMPLE)
    layers = srt_to_text_layers(entries)
    assert len(layers) == 3
    for layer in layers:
        assert "text" in layer
        assert "start" in layer
        assert "end" in layer
        assert "position" in layer


def test_empty_input_returns_empty():
    assert parse_srt("") == []
