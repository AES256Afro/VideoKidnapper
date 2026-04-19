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
`escape_drawtext_value()` or `escape_path()`.
"""


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
