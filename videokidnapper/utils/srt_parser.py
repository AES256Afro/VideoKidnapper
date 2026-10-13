# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Minimal SRT / WebVTT subtitle parser.

Returns a list of dicts compatible with TextLayersPanel's layer schema so a
user can import subtitles and immediately export with them baked in.
"""

import re
from pathlib import Path


# One timestamp: hours are optional (WebVTT writes "01:02.500" for clips
# under an hour, and so does openai-whisper's VTT output), and the
# fraction may have 1-3 digits ("1,5" is half a second, not 5 ms).
_TS = r"(?:(\d+):)?(\d{1,2}):(\d{1,2})[,.](\d{1,3})"
_TIMECODE = re.compile(_TS + r"\s*-->\s*" + _TS)

# Styling markup that would otherwise be burned into the video as text:
# SRT <i> <b> <u> <font ...>, WebVTT <c.yellow> <v Speaker> <lang en>
# <ruby>/<rt> and inline <00:00:01.000> timestamps, and the SSA override
# blocks such as {\an8} that many SRT files carry.
_TAGS = re.compile(
    r"</?(?:b|i|u|s|c|v|lang|ruby|rt|font)(?:[\s.][^>]*)?>"
    r"|<\d+:\d{2}(?::\d{2})?[.,]\d+>"
    r"|\{\\[^}]*\}",
    re.IGNORECASE,
)
# WebVTT escapes; "&amp;" last, so "&amp;lt;" stays "&lt;".
_ENTITIES = {"&lt;": "<", "&gt;": ">", "&nbsp;": " ", "&lrm;": "",
             "&rlm;": "", "&amp;": "&"}


def _tc_to_seconds(h, m, s, frac):
    return (int(h or 0) * 3600 + int(m) * 60 + int(s)
            + int(frac.ljust(3, "0")) / 1000)


def _clean(line):
    line = _TAGS.sub("", line)
    for entity, char in _ENTITIES.items():
        line = line.replace(entity, char)
    return line.strip()


def parse_srt(text):
    """Return a list of ``{start, end, text}`` dicts.

    Tolerant: SRT or WebVTT timestamps (comma or dot, hours optional),
    missing sequence numbers or blank lines, CRLF, a BOM; styling tags
    are removed and multi-line captions are joined with newlines. A cue
    that ends before it starts is skipped.

    A line of digits is a sequence number only when the timestamp line
    follows it; anywhere else it is a caption ("3", "2", "1"...).
    """
    lines = [line.strip() for line in text.lstrip("\ufeff").splitlines()]
    entries = []
    current = None

    def close():
        if current and current["text"] and current["end"] > current["start"]:
            entries.append(current)

    for i, stripped in enumerate(lines):
        m = _TIMECODE.search(stripped)
        if m:
            close()
            groups = m.groups()
            current = {
                "start": _tc_to_seconds(*groups[:4]),
                "end":   _tc_to_seconds(*groups[4:]),
                "text":  "",
            }
            continue
        if current is None:
            continue
        if stripped == "":
            if current["text"]:
                close()
                current = None
            continue
        if stripped.isdigit() and i + 1 < len(lines) and _TIMECODE.search(lines[i + 1]):
            continue    # the next cue's sequence number
        cleaned = _clean(stripped)
        if not cleaned:
            continue
        sep = "\n" if current["text"] else ""
        current["text"] = current["text"] + sep + cleaned
    close()
    return entries


def read_subtitle_text(path):
    """Decode a subtitle file: UTF-16 with a BOM, UTF-8 (BOM or not), or
    failing that Windows-1252, which older SRT files mostly are. Reading
    those as UTF-8 turned every accented letter into a replacement mark.
    """
    data = Path(path).read_bytes()
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")


def parse_srt_file(path):
    return parse_srt(read_subtitle_text(path))


def srt_to_text_layers(entries, style_preset="Subtitle"):
    """Turn parsed entries into TextLayersPanel-compatible layer dicts."""
    layers = []
    for e in entries:
        layers.append({
            "text":      e["text"],
            "start":     e["start"],
            "end":       e["end"],
            "style":     style_preset,
            "font":      "Arial",
            "fontsize":  24,
            "fontcolor": "white",
            "position":  "(w-tw)/2:h-th-20",
            "box":       True,
            "boxcolor":  "black@0.6",
            "boxborderw": 8,
        })
    return layers
