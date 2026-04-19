# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""VideoKidnapper — Video GIF/Clip Creator with Text Overlays.

This module is the single source of truth for the project version.
``pyproject.toml`` reads ``__version__`` via ``tool.setuptools.dynamic``,
and ``videokidnapper.config.APP_VERSION`` re-exports it so the rest of
the code (window title, update check, release-notes link) stays in sync
without a second place to bump.
"""
__version__ = "1.2.0"
