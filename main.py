#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""VideoKidnapper — repo-root shim.

Users who ``git clone`` the repo expect ``python main.py`` to Just Work;
users who ``pip install videokidnapper`` get the ``videokidnapper``
console script from ``pyproject.toml``. Both call the same entry point.
"""
from videokidnapper.cli import main


if __name__ == "__main__":
    main()
