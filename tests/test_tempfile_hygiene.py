# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Anti-regression tests for temporary-file hygiene.

``tempfile.mktemp`` reserves a *name* without creating the file, so two
concurrent exports (reachable since the Batch Export tab) can race to the
same path — and a local attacker can pre-create the predicted name. Every
scratch file must go through ``tempfile.mkstemp`` (or the shared
``_mkstemp_path`` helper in ``core/ffmpeg/_internals.py``), which creates
the file atomically.

The source scan below is deliberately dumb — it greps the package tree —
so the ban cannot quietly regress in a module nobody remembered to cover
with a behavioral test.
"""
import tempfile
from pathlib import Path

import videokidnapper


PACKAGE_ROOT = Path(videokidnapper.__file__).resolve().parent


def _source_files():
    return sorted(PACKAGE_ROOT.rglob("*.py"))


def test_no_mktemp_anywhere_in_package():
    offenders = []
    for path in _source_files():
        text = path.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), start=1):
            # Allow docstring/comment mentions that explain the history.
            code = line.split("#", 1)[0]
            if "mktemp(" in code and "mkstemp(" not in code:
                offenders.append(f"{path.relative_to(PACKAGE_ROOT)}:{lineno}")
    assert not offenders, (
        "tempfile.mktemp is banned (race-prone); use mkstemp via "
        "core/ffmpeg/_internals._mkstemp_path. Offenders: "
        + ", ".join(offenders)
    )


def test_mkstemp_path_creates_a_real_file():
    from videokidnapper.core.ffmpeg._internals import _mkstemp_path

    path = _mkstemp_path(".vidkid-test")
    try:
        # The file must actually exist — that is the whole point over
        # mktemp: nobody else can claim the name between calls.
        assert path.exists()
        assert path.suffix == ".vidkid-test"
        # And it must live in the system temp dir, not the CWD.
        # (resolve both sides: /var is a symlink to /private/var on macOS)
        tmpdir = Path(tempfile.gettempdir()).resolve()
        assert tmpdir in path.resolve().parents
    finally:
        path.unlink(missing_ok=True)


def test_mkstemp_path_never_repeats_a_name():
    from videokidnapper.core.ffmpeg._internals import _mkstemp_path

    paths = {_mkstemp_path(".vidkid-test") for _ in range(50)}
    try:
        assert len(paths) == 50
    finally:
        for p in paths:
            p.unlink(missing_ok=True)
