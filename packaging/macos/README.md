# macOS build

Builds **`VideoKidnapper-X.Y.Z-macos-arm64.dmg`** (Apple Silicon) and
**`-x86_64.dmg`** (Intel) — a standalone `.app`, no Python required. FFmpeg
is bundled.

## How it's built

`.github/workflows/macos.yml` on tag push, one job per arch (macos-14 =
Apple Silicon, macos-13 = Intel — PyInstaller can't cross-compile a `.app`,
so each architecture builds on its own runner):

1. `packaging/videokidnapper-macos.spec` → `dist/VideoKidnapper.app` (PyInstaller `BUNDLE`, `.icns` icon).
2. Static **ffmpeg/ffprobe** from [evermeet.cx](https://evermeet.cx/ffmpeg/) drop into `Contents/Resources/assets/ffmpeg/bin` — a `.app` has no reliable PATH, so the app's resolver (`videokidnapper/utils/ffmpeg_check.py`, frozen branch) looks next to the executable / in Resources.
3. `create-dmg` wraps it with an Applications drop-link (falls back to `hdiutil` if unavailable).

## Gatekeeper (unsigned)

Without an Apple Developer certificate ($99/yr) the app is unsigned and un-notarized, so a normal double-click is blocked on first run with "can't be opened." Users **right-click the app → Open** once, then it's trusted. This is documented on the release page and the website.

To remove the friction entirely: enroll in the Apple Developer Program, add `codesign` + `notarytool` steps (secrets: cert `.p12` + notarization credentials), and staple the ticket. Tracked as a budget decision in `docs/DISTRIBUTION-PLAN.md`.

## Licensing note

The bundled FFmpeg is a GPL static build. VideoKidnapper invokes it as a separate process (mere aggregation — the app stays Apache-2.0); the release notes link the source. To avoid GPL entirely, swap in an LGPL macOS build — but confirm it includes libx264, which the encoder fallback and GIF intermediate need.

## Local build (on a Mac)

```bash
pip install -r requirements.txt pyinstaller
python -m PyInstaller packaging/videokidnapper-macos.spec --noconfirm --clean
# then drop ffmpeg/ffprobe into
#   dist/VideoKidnapper.app/Contents/Resources/assets/ffmpeg/bin
open dist/VideoKidnapper.app
```
