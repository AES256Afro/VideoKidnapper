# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
#
# PyInstaller spec for the macOS .app bundle (wrapped into a .dmg by
# .github/workflows/macos.yml). Run on macOS from the repo root:
#
#   python -m PyInstaller packaging/videokidnapper-macos.spec --noconfirm --clean
#
# Produces dist/VideoKidnapper.app. FFmpeg is bundled into
# Contents/Resources/assets/ffmpeg/bin (the workflow drops it there
# after the build) — a .app has no reliable PATH, same reasoning as the
# MSIX container.

# mypy: ignore-errors
# ruff: noqa

from PyInstaller.utils.hooks import collect_all, collect_data_files

block_cipher = None

ctk_datas, ctk_binaries, ctk_hiddenimports = collect_all("customtkinter")
try:
    dnd_datas, dnd_binaries, dnd_hiddenimports = collect_all("tkinterdnd2")
except Exception:
    dnd_datas, dnd_binaries, dnd_hiddenimports = [], [], []

# OpenCV (cv2) for ⚡ auto-track — lazy import, collected explicitly.
# Guarded so a build host without opencv still yields a working app.
try:
    cv2_datas, cv2_binaries, cv2_hiddenimports = collect_all("cv2")
except Exception:
    cv2_datas, cv2_binaries, cv2_hiddenimports = [], [], []

pil_datas = collect_data_files("PIL")

datas = ctk_datas + dnd_datas + cv2_datas + pil_datas + [
    ("../videokidnapper/assets/icon.png", "videokidnapper/assets"),
]
binaries = ctk_binaries + dnd_binaries + cv2_binaries
hiddenimports = (ctk_hiddenimports + dnd_hiddenimports + cv2_hiddenimports
                 + ["yt_dlp.extractor"])

a = Analysis(
    ["../main.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["matplotlib", "pandas", "IPython", "jupyter", "notebook"],
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="VideoKidnapper",
    debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
    console=False,
)

coll = COLLECT(
    exe, a.binaries, a.zipfiles, a.datas,
    strip=False, upx=False, name="VideoKidnapper",
)

app = BUNDLE(
    coll,
    name="VideoKidnapper.app",
    icon="../videokidnapper/assets/icon.icns",
    bundle_identifier="com.aes256.videokidnapper",
    info_plist={
        "CFBundleName": "VideoKidnapper",
        "CFBundleDisplayName": "VideoKidnapper",
        "NSHighResolutionCapable": True,
        # Tk apps are not document-based; declare no URL types.
        "LSMinimumSystemVersion": "11.0",
    },
)
