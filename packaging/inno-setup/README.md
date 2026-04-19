# Inno Setup installer

Builds **`VideoKidnapper-Setup-X.Y.Z.exe`** — the proper Windows installer that wraps the PyInstaller portable `.exe` in a Setup wizard, adds a Start Menu shortcut, registers in Programs & Features, and handles uninstall cleanly.

Both files ship on every GitHub Release:

| File | Who it's for |
|---|---|
| `VideoKidnapper-Setup-X.Y.Z.exe` | 90% of Windows users — wants an installer |
| `VideoKidnapper.exe` | Portable users — download, double-click, run from anywhere |

## How it's built

`.github/workflows/installer.yml` runs on tag push:

1. PyInstaller produces `dist/VideoKidnapper.exe` (portable binary).
2. `choco install innosetup -y` drops `iscc.exe` on PATH.
3. `iscc /DMyAppVersion=<tag> packaging/inno-setup/videokidnapper.iss` compiles the wizard, referencing the portable `.exe` from step 1.
4. Both files get uploaded as CI artifacts + attached to the GitHub Release.

## Building locally (optional)

If you want to produce a Setup `.exe` from your dev box:

```powershell
# 1. Build the portable .exe first
pyinstaller packaging\videokidnapper.spec --noconfirm --clean

# 2. Install Inno Setup 6.x if you don't have it
choco install innosetup -y
# (or download the installer from https://jrsoftware.org/isdl.php)

# 3. Compile the installer
iscc.exe /DMyAppVersion=1.2.0 packaging\inno-setup\videokidnapper.iss
```

Output lands at `dist/VideoKidnapper-Setup-1.2.0.exe`.

## What the installer does

- Default install path: `%LOCALAPPDATA%\Programs\VideoKidnapper` (per-user, no admin prompt on modern Windows).
- Power users can opt into machine-wide install via the "Install for all users" question in the wizard.
- Creates a Start Menu shortcut under `VideoKidnapper`.
- Optional desktop shortcut (off by default; user opts in).
- Registers in **Programs & Features** so uninstall is one click from Windows' standard flow.
- Offers a "Launch VideoKidnapper" checkbox at the end (unchecked by default).

## What the installer does NOT do

- **No FFmpeg bundle.** Same as the portable build — the in-app Setup dialog handles it on first launch. Adding ffmpeg.exe (50+ MB) to the installer would bloat it badly and complicate GPL-vs-LGPL-build licensing.
- **No auto-update mechanism.** The app already checks GitHub for new releases on launch (`videokidnapper/utils/github_update.py`); the installer itself doesn't re-check.
- **No user-settings removal on uninstall.** `~/.videokidnapper_settings.json` is deliberately preserved so a reinstall picks up where the user left off. Users who want a clean wipe can delete the JSON by hand.
- **No code signing.** Unsigned `.exe`s trigger SmartScreen warnings on first run; addressing this needs an EV certificate (ongoing cost + maintainer setup). Left for a future release cadence.

## Inno Setup version

Script targets **Inno Setup 6.x** (what the `choco install innosetup` package currently pins). The `ArchitecturesAllowed` / `ArchitecturesInstallIn64BitMode` values use the newer `x64compatible` identifier; anyone compiling with Inno Setup 5.x will need to swap those for `x64` (older identifier, same meaning).

## AppId — do not change

```
AppId={{8C8E1A2F-5D4B-4E6A-9F32-7C1A5B2D6E84}
```

Inno Setup uses this GUID to find previous installs when users upgrade. Changing it turns every upgrade into a side-by-side install, leaving orphan Start Menu entries and duplicate Programs & Features rows. **The GUID is permanent** — even across major version bumps.

If you ever need to break compatibility (e.g. migrate the install root), use the standard Inno Setup `[Code]` section to run a pre-install script that cleans up the old install, rather than changing `AppId`.
