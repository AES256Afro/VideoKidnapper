# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Enforces that every Python file in the repo carries the SPDX Apache-2.0
marker at the top.

This is the tripwire for the project's "all code stays Apache-2.0" policy.
CI runs this test on every PR, so a contributor who forgets the header
gets a failing check before their change can merge.
"""

import pathlib


ROOT = pathlib.Path(__file__).resolve().parent.parent
SKIP_DIRS = {
    ".git", "__pycache__", "build", "dist",
    ".venv", "venv", "env",
    ".pytest_cache", ".ruff_cache", ".mypy_cache",
    "assets",
}
REQUIRED_MARKER = "SPDX-License-Identifier: Apache-2.0"


def _python_files():
    for p in ROOT.rglob("*.py"):
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        yield p


def test_every_python_file_has_apache_spdx_header():
    missing = []
    for path in _python_files():
        # Read just the opening of the file — the SPDX marker lives in the
        # first couple of comment lines, right after any shebang.
        head = path.read_text(encoding="utf-8", errors="replace")[:500]
        if REQUIRED_MARKER not in head:
            missing.append(str(path.relative_to(ROOT)))
    assert not missing, (
        "The following files are missing the Apache-2.0 SPDX header. Add "
        "these two lines to the top (below any shebang):\n\n"
        "    # SPDX-FileCopyrightText: 2026 Your Name <contact>\n"
        "    # SPDX-License-Identifier: Apache-2.0\n\n"
        "Missing files:\n  " + "\n  ".join(missing)
    )
