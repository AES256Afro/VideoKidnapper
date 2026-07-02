# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
#
# PyInstaller spec for the Linux one-dir build that the AppImage wraps.
#
# Run from the repo root (on Linux):
#
#   python -m PyInstaller packaging/videokidnapper-linux.spec --noconfirm --clean
#
# Produces ``dist/VideoKidnapper/`` (a one-dir bundle). The AppImage
# workflow at ``.github/workflows/appimage.yml`` assembles it into an
# AppDir together with an LGPL FFmpeg and runs appimagetool.
#
# Why one-dir here when Windows ships one-file: an AppImage is already a
# single self-mounting file, so a one-file PyInstaller binary inside it
# would just add a second extraction step (and startup latency) for
# nothing.

# mypy: ignore-errors
# ruff: noqa

from PyInstaller.utils.hooks import collect_all, collect_data_files

block_cipher = None

ctk_datas, ctk_binaries, ctk_hiddenimports = collect_all("customtkinter")
try:
    dnd_datas, dnd_binaries, dnd_hiddenimports = collect_all("tkinterdnd2")
except Exception:
    # Optional dep — fine if it's not installed on the build host.
    dnd_datas, dnd_binaries, dnd_hiddenimports = [], [], []

pil_datas = collect_data_files("PIL")

datas = ctk_datas + dnd_datas + pil_datas + [
    # Window icon: dest mirrors the package layout so
    # Path(__file__).parent / "assets" resolves inside the bundle.
    ("../videokidnapper/assets/icon.png", "videokidnapper/assets"),
    ("../videokidnapper/assets/icon.ico", "videokidnapper/assets"),
]
binaries = ctk_binaries + dnd_binaries
hiddenimports = ctk_hiddenimports + dnd_hiddenimports + [
    "yt_dlp.extractor",
]


a = Analysis(
    ["../main.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "matplotlib",
        "pandas",
        "IPython",
        "jupyter",
        "notebook",
    ],
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,   # one-dir: binaries live in COLLECT below
    name="VideoKidnapper",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="VideoKidnapper",
)
