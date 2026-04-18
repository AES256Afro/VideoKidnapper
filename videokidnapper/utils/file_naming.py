# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Deterministic export file-name generator.

Emits ``VidKid_<mode>_<YYYYMMDD>_<HHMMSS>[.n].<ext>`` under ``base_dir``
(or ``DOWNLOADS_DIR`` by default). The ``_n`` suffix only appears when
a same-second filename collision happens, which is rare but real for
rapid back-to-back exports of a multi-range queue.
"""
from datetime import datetime
from pathlib import Path
from typing import Optional, Union

from videokidnapper.config import DOWNLOADS_DIR


PathLike = Union[str, Path]


def generate_export_path(
    mode: str,
    extension: str,
    base_dir: Optional[PathLike] = None,
) -> Path:
    """Return a new, unique export path under ``base_dir``.

    ``mode`` appears in the filename (typical values: ``trim``, ``cli``,
    ``record``, ``trim_concat``). ``extension`` may be dotted or bare —
    both ``"mp4"`` and ``".mp4"`` work.
    """
    resolved_base: Path = Path(base_dir) if base_dir else DOWNLOADS_DIR
    resolved_base.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = f"VidKid_{mode}_{timestamp}"
    ext = extension.lower().lstrip(".")
    output = resolved_base / f"{base_name}.{ext}"
    counter = 1
    while output.exists():
        output = resolved_base / f"{base_name}_{counter}.{ext}"
        counter += 1
    return output
