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


# --- drawtext position expressions -----------------------------------------
#
# ``x={x_expr}:y={y_expr}`` is interpolated bare into the filter spec,
# exactly like colours — so a crafted ``position`` in a ``.vidkid``
# project file can terminate the option (``:``), the filter (``,`` /
# ``;``), or the whole graph (``[``/``]``) and inject arbitrary filters,
# including the file-reading ``movie=`` source. Same class of bug the
# v1.8.1 colour fix closed, one field over.
#
# Legitimate values are exactly two shapes:
#
# 1. the anchor presets from ``config.POSITION_MAP`` — drawtext frame
#    variables and arithmetic only: ``(w-tw)/2:h-th-20``, ``w-tw-20:20``;
# 2. numeric drag positions: ``960:540`` (source-pixel ints/floats,
#    possibly negative mid-drag).
#
# The allowlist below encodes that: one ``:`` separator, and each side
# built solely from digits, letters (frame variables), arithmetic
# operators, parentheses, dots, and spaces. No character that lavfi
# treats as structure can appear, so the value can never break out of
# the option it is interpolated into.
DEFAULT_POSITION = "(w-tw)/2:h-th-20"

_SAFE_EXPR_PART_RE = re.compile(r"^[0-9A-Za-z_+\-*/(). ]{1,100}$")
_POSITION_PAIR_RE = re.compile(r"^-?\d+(?:\.\d+)?:-?\d+(?:\.\d+)?$")


def sanitize_position_expr(value: "str | None",
                           default: str = DEFAULT_POSITION) -> str:
    """Return ``value`` if it is a safe drawtext ``x:y`` position, else
    ``default``.

    Validation — not escaping — is the right tool here for the same
    reason as :func:`sanitize_color`: the value is interpolated without
    containing quotes, and a value that needs escaping is by definition
    not a position the UI could have produced. Falling back to the
    default keeps a corrupt or hostile project openable.
    """
    if value is None:
        return default
    text = str(value).strip()
    if _POSITION_PAIR_RE.match(text):
        return text
    if text.count(":") != 1:
        return default
    x_part, y_part = text.split(":", 1)
    if _SAFE_EXPR_PART_RE.match(x_part) and _SAFE_EXPR_PART_RE.match(y_part):
        return text
    return default
