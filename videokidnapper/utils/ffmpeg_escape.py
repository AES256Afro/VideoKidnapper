# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""FFmpeg filter-graph escaping.

The `drawtext` filter runs arbitrary user text through ffmpeg's lavfi parser,
which has four layers of escaping:

1. Shell (we bypass this with argv-style subprocess).
2. Filter-graph: `[]`, `,`, `;`, and backslash are special.
3. Filter argument: `:` separates options, `=` separates key from value.
4. drawtext-specific: single quotes delimit the text; `\n` is a newline.

Without careful escaping, a user typing `a:b;c[d]` in a text layer can break
the filter graph or — worse — smuggle extra options like `textfile=…`.
Every value that ends up inside a filter spec should flow through
`escape_drawtext_value()`, `escape_path()`, or `sanitize_color()`.

Colours are a separate case: they are *not* quoted in the filter spec
(`fontcolor=white`), so escaping is the wrong tool — the value has to be
rejected outright if it is not a colour. See `sanitize_color()`.
"""

import re


_DRAWTEXT_ESCAPES = {
    "\\": "\\\\",
    ":":  "\\:",
    "'":  "\u2019",      # curly-quote substitute; ffmpeg's escape story for
                          # single quotes inside single-quoted strings is messy,
                          # and the curly quote looks identical to users.
    "%":  "\\%",
    "[":  "\\[",
    "]":  "\\]",
    ",":  "\\,",
    ";":  "\\;",
}


def escape_drawtext_value(text: "str | None") -> str:
    """Escape a string for use as the value in a drawtext option.

    The returned string is safe to wrap in single quotes inside the filter
    spec, e.g. ``text='<escaped>'``.
    """
    if text is None:
        return ""
    out = []
    for ch in str(text):
        out.append(_DRAWTEXT_ESCAPES.get(ch, ch))
    return "".join(out)


def escape_path(path: "str | None") -> str:
    """Escape a filesystem path for use in an ffmpeg filter argument.

    On Windows, forward slashes are preferred and drive-letter colons must be
    escaped. Backslashes and single quotes are also escaped so the value can
    be wrapped in single quotes.
    """
    if path is None:
        return ""
    p = str(path).replace("\\", "/")
    # Now escape characters that remain problematic inside filter args.
    p = p.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\u2019")
    return p


def quote_filter_value(escaped: str) -> str:
    """Wrap an already-escaped string in single quotes for lavfi."""
    return f"'{escaped}'"


# ffmpeg accepts a named colour ("white", "Crimson", "random"), an
# `#RRGGBB[AA]` / `0xRRGGBB[AA]` literal, and an optional `@alpha`
# suffix. Anything else is not a colour.
_COLOR_RE = re.compile(
    r"""^(?:
        \#[0-9A-Fa-f]{6}(?:[0-9A-Fa-f]{2})?     # #RRGGBB / #RRGGBBAA
      | 0x[0-9A-Fa-f]{6}(?:[0-9A-Fa-f]{2})?     # 0xRRGGBB / 0xRRGGBBAA
      | [A-Za-z][A-Za-z0-9]{0,31}               # named colour, incl. "random"
    )
    (?:@(?:0|1|0?\.[0-9]{1,6}|1\.0+))?$         # optional @alpha
    """,
    re.VERBOSE,
)


def sanitize_color(value: "str | None", default: str = "white") -> str:
    """Return ``value`` if it is a valid ffmpeg colour, else ``default``.

    Colour options are interpolated bare into the filter spec
    (``fontcolor=white``), with no surrounding quotes to contain them.
    A value carrying ``,`` or ``:`` therefore terminates the option and
    the rest is parsed as *more filter graph* — so a hand-edited or
    downloaded ``.vidkid`` project could smuggle in extra filters. The
    ``movie=`` source filter reads arbitrary local files, which turns
    this into file disclosure rather than a cosmetic glitch.

    Escaping is not the fix here: an escaped colour is not a valid
    colour, so ffmpeg would fail the encode. Invalid input falls back to
    the default instead, which keeps a corrupt project openable.

    ``default`` is trusted (it comes from our own config), so it is
    returned as-is without re-validation.
    """
    if value is None:
        return default
    text = str(value).strip()
    return text if _COLOR_RE.match(text) else default
