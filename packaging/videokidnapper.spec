# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
#
# PyInstaller spec for the one-file Windows .exe build.
#
# Run from the repo root:
#
#   pyinstaller packaging/videokidnapper.spec --noconfirm --clean
#
# Produces ``dist/VideoKidnapper.exe`` (single-file, ~30 MB) that users
# can run without a Python install. The GitHub Actions workflow at
# ``.github/workflows/installer.yml`` invokes this on every tag push.
#
# Why a spec file rather than CLI flags in the workflow: the
# ``collect_*`` helpers used below grab every data file that
# customtkinter / tkinterdnd2 ship inside their packages (theme JSON,
# DLLs, TCL resources) — a plain ``--collect-all`` command line can
# miss these under newer PyInstaller versions. The spec pins the
# behavior so the workflow build matches a local build.

# mypy: ignore-errors
# ruff: noqa

from PyInstaller.utils.hooks import collect_all, collect_data_files

block_cipher = None

# customtkinter ships its theme JSON as package data. tkinterdnd2 ships
# native TCL source in its share/ folder — both need to be bundled.
ctk_datas, ctk_binaries, ctk_hiddenimports = collect_all("customtkinter")
try:
    dnd_datas, dnd_binaries, dnd_hiddenimports = collect_all("tkinterdnd2")
except Exception:
    # Optional dep — fine if it's not installed on the build host.
    dnd_datas, dnd_binaries, dnd_hiddenimports = [], [], []

# Pillow's ImageTk needs tk itself, which PyInstaller bundles automatically.
pil_datas = collect_data_files("PIL")

datas = ctk_datas + dnd_datas + pil_datas
binaries = ctk_binaries + dnd_binaries
hiddenimports = ctk_hiddenimports + dnd_hiddenimports + [
    # yt_dlp subpackages occasionally slip past the auto-discovery;
    # hiddenimports makes sure its extractor registry is bundled.
    "yt_dlp.extractor",
]


a = Analysis(
    ["../main.py"],            # repo-root shim; pulls in the package graph
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Trim the wheel: we don't ship Jupyter/IPython/matplotlib even
        # though they may be pip-installed alongside numpy on CI hosts.
        "matplotlib",
        "pandas",
        "IPython",
        "jupyter",
        "notebook",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="VideoKidnapper",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,          # UPX trips some AV engines; not worth the flag.
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,      # --windowed: no console window on double-click
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
