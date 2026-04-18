"""Minimal SRT subtitle parser.

Returns a list of dicts compatible with TextLayersPanel's layer schema so a
user can import subtitles and immediately export with them baked in.
"""

import re
from pathlib import Path


_TIMECODE = re.compile(
    r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)"
)


def _tc_to_seconds(h, m, s, ms):
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


def parse_srt(text):
    """Return a list of ``{start, end, text}`` dicts.

    Tolerant: accepts both SRT comma-separated milliseconds and VTT-style
    dot separation; ignores missing sequence numbers; joins multi-line
    captions with newlines.
    """
    entries = []
    current = None
    for line in text.splitlines():
        stripped = line.strip()
        m = _TIMECODE.search(stripped)
        if m:
            if current and current.get("text"):
                entries.append(current)
            current = {
                "start": _tc_to_seconds(*m.groups()[:4]),
                "end":   _tc_to_seconds(*m.groups()[4:]),
                "text":  "",
            }
            continue
        if current is None:
            continue
        if stripped == "":
            if current.get("text"):
                entries.append(current)
                current = None
            continue
        if stripped.isdigit() and not current.get("text"):
            # Sequence number line — skip.
            continue
        sep = "\n" if current["text"] else ""
        current["text"] = current["text"] + sep + stripped
    if current and current.get("text"):
        entries.append(current)
    return entries


def parse_srt_file(path):
    p = Path(path)
    text = p.read_text(encoding="utf-8-sig", errors="replace")
    return parse_srt(text)


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
