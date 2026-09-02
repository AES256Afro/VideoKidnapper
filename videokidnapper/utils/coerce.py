# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Fail-soft numeric conversion for values read out of project files.

`.vidkid` files are portable by design — sharing one is a feature — and
`project_files.load_document` validates their *structure* without
inspecting the contents of a layer dict. So every number a layer
carries (`fontsize`, `borderw`, `scale`, `start`…) is untrusted input
that may be a string, `None`, or missing entirely.

These live here, rather than beside either consumer, because both the
export and the preview read the *same* layer dicts and must agree about
them. They did not: 1.8.2 hardened the ffmpeg filter builders but left
the preview canvas calling bare `int()`, so a project with
`"fontsize": "abc"` exported cleanly and crashed the preview with a
`ValueError`. One definition, imported by both, is what keeps that from
drifting apart again.

The contract is deliberately quiet: bad input becomes the default
rather than raising. A corrupt project should still open, with the
affected layer rendered at sane values, instead of taking down the
editor.
"""


def coerce_int(value, default=0):
    """``int(value)``, or ``default`` when that is not possible."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def coerce_float(value, default=0.0):
    """``float(value)``, or ``default`` when that is not possible.

    Also rejects NaN and the infinities: they convert without error but
    poison any arithmetic downstream, and an infinite coordinate in a
    filter expression is not something ffmpeg or Pillow handles well.
    """
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    if result != result or result in (float("inf"), float("-inf")):
        return default
    return result
