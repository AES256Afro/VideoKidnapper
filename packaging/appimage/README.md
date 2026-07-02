# Linux AppImage

Builds **`VideoKidnapper-x86_64.AppImage`** — the download-and-run Linux binary. No Python, no FFmpeg install, no root. This is the recommended route on immutable distros (Bazzite, SteamOS, Fedora Silverblue) where you can't layer packages.

## How it's built

`.github/workflows/appimage.yml` runs on tag push (and on manual dispatch for test builds from any branch):

1. PyInstaller builds a **one-dir** bundle from `packaging/videokidnapper-linux.spec` (one-dir, not one-file: the AppImage is already a single self-mounting file, so one-file would just add a second extraction step).
2. A **GPL FFmpeg** (BtbN's `linux64-gpl` build) is downloaded and dropped into `AppDir/usr/bin/`.
3. `AppRun` prepends `usr/bin` to `PATH`, so the app's normal `shutil.which("ffmpeg")` lookup finds the bundled copy — no code changes needed.
4. `appimagetool` squashes the AppDir into the final AppImage.
5. A `--help` smoke test runs (argparse handles it before Tk needs a display).

Built on **ubuntu-22.04** deliberately: the runner's glibc (2.35) is the oldest version the binary requires, so it runs on Ubuntu 22.04+, Debian 12+, Fedora 36+, Bazzite, and SteamOS 3+. Don't switch the job to `ubuntu-latest` without understanding that this raises the floor.

## What users do

```bash
chmod +x VideoKidnapper-x86_64.AppImage
./VideoKidnapper-x86_64.AppImage
```

Optional desktop integration (menu entry, icon): use [Gear Lever](https://flathub.org/apps/it.mijorus.gearlever) or [appimaged](https://github.com/probonopd/go-appimage).

## Licensing note — why the GPL FFmpeg build (not LGPL)

BtbN's **LGPL** variant was considered first, but it lacks **libx264** — which the app hardcodes as both the software-encoder fallback (`core/ffmpeg/_internals.py::pick_encoder`) and the GIF image-overlay intermediate pass (`core/ffmpeg/encode.py`). Bundling LGPL would break MP4 export on machines without hardware encoders and GIF-with-overlay export everywhere.

The GPL build is fine to bundle because:

- VideoKidnapper invokes `ffmpeg` as a **separate process** — that's *mere aggregation* under the GPL, so the app itself stays Apache-2.0.
- The only obligation is source availability **for FFmpeg itself**: BtbN publishes the exact sources with every build, and our release notes link there.

If you ever swap the FFmpeg URL, either keep a build that includes libx264 or first make the encoder fallback probe-aware.

## Local build (on any Linux box)

```bash
pip install -r requirements.txt pyinstaller
python -m PyInstaller packaging/videokidnapper-linux.spec --noconfirm --clean
# then follow the AppDir assembly steps in .github/workflows/appimage.yml
```

## Testing a branch build without a release

Actions → **Linux AppImage** → *Run workflow* → pick the branch, leave `tag` empty. The AppImage lands as a CI artifact instead of on a release.
