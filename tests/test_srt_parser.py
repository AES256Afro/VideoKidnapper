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


# ---------------------------------------------------------------------------
# Edge cases from real files
# ---------------------------------------------------------------------------

def test_vtt_without_hours():
    """WebVTT leaves out the hours under an hour (openai-whisper's VTT
    does too). Every such cue was dropped: "No subtitle entries found"."""
    vtt = "WEBVTT\n\n00:01.000 --> 00:04.000\nHello\n\n01:05.5 --> 01:07.250\nWorld\n"
    assert parse_srt(vtt) == [
        {"start": 1.0, "end": 4.0, "text": "Hello"},
        {"start": 65.5, "end": 67.25, "text": "World"},
    ]


def test_short_fractions_are_padded():
    """"1,5" is half a second, not five milliseconds."""
    (entry,) = parse_srt("1\n00:00:01,5 --> 00:00:02,25\nhalf\n")
    assert (entry["start"], entry["end"]) == (1.5, 2.25)


def test_numeric_captions_are_kept():
    """A caption that is just a number ("3", "2", "1"...) was taken for a
    sequence number and dropped."""
    srt = ("1\n00:00:01,000 --> 00:00:02,000\n3\n\n"
           "2\n00:00:02,000 --> 00:00:03,000\n1984\n\n"
           "3\n00:00:03,000 --> 00:00:04,000\nGo!\n")
    assert [e["text"] for e in parse_srt(srt)] == ["3", "1984", "Go!"]


def test_missing_blank_lines():
    srt = ("1\n00:00:01,000 --> 00:00:02,000\nHello\n"
           "2\n00:00:03,000 --> 00:00:04,000\nThere\n")
    assert [e["text"] for e in parse_srt(srt)] == ["Hello", "There"]


def test_styling_tags_are_not_burned_in():
    srt = ("1\n00:00:01,000 --> 00:00:02,000\n"
           r"<i>Whispering</i>" "\n"
           r"{\an8}<font color=\"#ffff00\">Top</font> & <b>bold</b>" "\n")
    assert parse_srt(srt)[0]["text"] == "Whispering\nTop & bold"


def test_vtt_markup_and_entities():
    vtt = ("WEBVTT\n\nNOTE written by hand\n\nintro\n"
           "00:00:01.000 --> 00:00:02.000 align:start position:10%\n"
           "<v Bob>Hi <c.yellow>there</c> <00:00:01.500>&lt;3 &amp;lt;\n")
    assert parse_srt(vtt) == [{"start": 1.0, "end": 2.0, "text": "Hi there <3 &lt;"}]


def test_a_heart_is_not_a_tag():
    (entry,) = parse_srt("1\n00:00:01,000 --> 00:00:02,000\nI <3 you > all\n")
    assert entry["text"] == "I <3 you > all"


def test_backwards_cue_is_skipped():
    srt = ("1\n00:00:05,000 --> 00:00:02,000\nbackwards\n\n"
           "2\n00:00:06,000 --> 00:00:07,000\nfine\n")
    assert [e["text"] for e in parse_srt(srt)] == ["fine"]


def test_crlf_and_bom():
    assert parse_srt("\ufeff1\r\n00:00:01,000 --> 00:00:02,000\r\nHi\r\n\r\n") == [
        {"start": 1.0, "end": 2.0, "text": "Hi"}]


def test_windows_1252_file(tmp_path):
    """Older SRT files are mostly Windows-1252; read as UTF-8 every
    accented letter became a replacement mark."""
    from videokidnapper.utils.srt_parser import parse_srt_file

    path = tmp_path / "old.srt"
    path.write_bytes("1\n00:00:01,000 --> 00:00:02,000\nCafé, déjà vu\n".encode("cp1252"))
    assert parse_srt_file(path)[0]["text"] == "Café, déjà vu"


def test_utf16_file(tmp_path):
    from videokidnapper.utils.srt_parser import parse_srt_file

    path = tmp_path / "notepad.srt"
    path.write_text("1\n00:00:01,000 --> 00:00:02,000\nŻółw\n", encoding="utf-16")
    assert parse_srt_file(path)[0]["text"] == "Żółw"


def test_utf8_file_with_bom(tmp_path):
    from videokidnapper.utils.srt_parser import parse_srt_file

    path = tmp_path / "bom.srt"
    path.write_text("1\n00:00:01,000 --> 00:00:02,000\nnaïve\n", encoding="utf-8-sig")
    assert parse_srt_file(path)[0]["text"] == "naïve"
