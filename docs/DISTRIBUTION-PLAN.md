# Distribution & Competitive Plan

How VideoKidnapper reaches users **without them running Python commands**, plus the
competitive context that motivates it. Companion to `docs/ROADMAP.md` (feature work)
and `docs/RELEASE.md` (the existing release playbook).

Priority/effort keys match the roadmap: **S** = < 1 day, **M** = 1–3 days,
**L** = a week or more.

---

## 1. Where VideoKidnapper sits

The niche is unusual: **one offline desktop app that both *downloads* clips (yt-dlp)
and *edits* them** (trim, crop, caption, GIF/MP4 export) — no watermark, no upload,
no account. Nearly every competitor does only one half of that.

The one-line pitch to lead with:

> **Download, trim, and caption clips into polished GIFs or MP4s — fully offline, no
> watermark, no account.**

## 2. Competitor landscape

**Bucket A — yt-dlp GUIs (download only, no editing):**

- [Open Video Downloader / Parabolic](https://github.com/jly0242/youtube-dl-gui) — cross-platform, paste-and-download, free
- [yt-dlp app](https://yt-dlp.app/) — auto-installs yt-dlp + FFmpeg on first launch, 1,510+ sites, Win/Mac/Linux
- [YT DLP GUI](https://ytdlpgui.com/) — clean Win/Mac app, built-in update checker
- Stacher, 4K Video Downloader (commercial)

**Bucket B — GIF / caption makers (edit only, mostly web):**

- [ezgif](https://ezgif.com/add-text), [Kapwing](https://www.kapwing.com/tools/add-text/gif), [Canva](https://www.canva.com/features/add-text-to-gif/), [VEED](https://www.veed.io/tools/add-text-to-video/add-text-to-gif), [Clideo](https://clideo.com/add-text-to-gif) — browser-based, watermarks / paywalls common
- [ScreenToGif](https://www.screentogif.com/) — closest *desktop* analog (record + edit + GIF), Windows-only
- [MiniTool MovieMaker](https://moviemaker.minitool.com/moviemaker/gif-caption-maker.html) — desktop GIF captioner

**Bucket C — full social-clip editors:**

- CapCut, Microsoft Clipchamp, [Descript](https://www.descript.com/tools/add-text-gif), Opus Clip (AI auto-clip), Shotcut / Kdenlive (open-source NLEs), HandBrake (transcode only)

**Direct competition** = the overlap of A + B: someone who downloads a clip *and*
captions it for social. Very few tools do both offline; the closest (CapCut) is
cloud-tied and telemetry-heavy and doesn't download.

## 3. Feature gaps (vs. the field)

Most of these are already tracked in `docs/ROADMAP.md`; the roadmap is in good shape.

| Gap | Who has it | Impact | Roadmap |
|---|---|---|---|
| Audio / music overlay track | Every social editor | **High** | 4.2 (P1/L) |
| AI auto-clip / highlight detection | Opus Clip, CapCut | **High** | new — silence-cut 4.3 is the cheap first step |
| Target-file-size GIF export ("fit under 8 MB") | ezgif | **High** | 3.5 |
| More platforms (TikTok, Twitch, Vimeo) | All yt-dlp GUIs | **High & cheap** | 4.4 (~1 day) |
| Auto-updating yt-dlp inside the frozen binary | yt-dlp app, YT DLP GUI | **High** | new — see Phase 4 below |
| True draggable timeline | All NLEs | Medium | — |
| WebP / APNG output | ezgif, modern web tools | Medium | 3.8 |
| Boomerang / reverse GIF | Every GIF tool | Medium | 3.4 |
| Project save/load | All editors | Medium | 4.5 |
| Word-level / karaoke captions | CapCut, Descript | Medium | 2.8 |

The genuinely *new* strategic gaps (not already on the roadmap): **(1)** auto-updating
yt-dlp inside the frozen binary, **(2)** AI auto-clip as a headline feature, **(3)**
cross-platform distribution (this document).

## 4. Benefits to lead with

1. **Download + edit + caption, offline, no watermark, no account** — nobody else has all four.
2. **Privacy / offline** — vs. cloud tools that upload your video.
3. **Preview == export fidelity** — pixel-accurate drawtext parity beats GIF web tools that guess.
4. **Free & open source (Apache-2.0)** — vs. CapCut telemetry / paywalls.

---

## 5. Packaging reality check

The **Windows story is ~90% built already**:

- `packaging/videokidnapper.spec` — working PyInstaller one-file spec
- `.github/workflows/installer.yml` — builds `VideoKidnapper.exe` **and** an Inno Setup
  wizard on every tag push, attaches both to the GitHub Release
- `packaging/winget/` + `packaging/homebrew/` manifests
- README already documents "Option A — Windows .exe, no Python required"

| Platform | Status | Gap |
|---|---|---|
| **Windows** | ~90% done | Never actually *shipped* (no tag pushed — roadmap 6.1). FFmpeg external. Unsigned → SmartScreen. |
| **Linux** | 0% | No AppImage / Flatpak / .deb. Homebrew-on-Linux still needs Python. |
| **macOS** | ~20% | Only a Homebrew formula (needs Python via brew). No `.app` / `.dmg`. |

So "run without Python" is **already solved on Windows** — it needs a version tag to
trigger the existing CI. The real work is **Linux + macOS binaries + bundling FFmpeg**.

### Decision: bundle FFmpeg

Bundle an **LGPL** FFmpeg build inside every artifact so the app works with zero setup.
LGPL avoids the GPL source-offer obligation the README flags for gyan.dev `essentials`
builds. Adds ~50–80 MB; removes the #1 first-run friction. The binary resolver checks the
bundled path first, then PATH, then the Setup-dialog download as a last resort.

### Decision: MSIX via the Microsoft Store (Windows "installed" path)

MSIX **does not replace** the PyInstaller `.exe` — it replaces the Inno Setup installer
*around* it. Build `VideoKidnapper.exe` with PyInstaller, then package that into an
`.msix`. Why:

- **Clean install/uninstall + auto-update** via App Installer (better than Inno Setup).
- **Free code signing through the Store** — Microsoft signs the package, which **kills
  the SmartScreen warning** for a **$19 one-time** individual dev account (vs. $200–400/yr
  for an OV/EV cert). This folds Windows code-signing (roadmap 6.2) in for near-free.

Catches specific to this app:

- MSIX **must be signed to install at all**; only the Store path gives free signing.
- MSIX runs in a **container with filesystem virtualization**. Two features need testing
  under it: **browser-cookie reads** (`yt-dlp --cookies-from-browser` reaching into
  Chrome/Firefox profiles — needs the `runFullTrust` capability and may still be
  restricted) and the **`~/.videokidnapper_settings.json` write**. FFmpeg subprocess
  calls and file pickers are fine.
- Windows 10+ only; Store certification adds review latency.

**Keep the portable `.exe`** for users who can't/won't use the Store. Budget a half-day
to verify cookie reads + settings writes inside the container before committing to MSIX.

---

## 6. The plan

Recommended order: **Phase 0 → 2 → 3 → 1 → 4 → Store/MSIX**. Ship Windows immediately
(it's done), get Linux + macOS binaries out for reach, then polish with FFmpeg bundling
and the updater, and layer MSIX on last.

### Phase 0 — Ship what's already built (Windows) — **S (~0.5 day)**

Fastest win on the list.

1. Finish roadmap 6.1 release gates: configure PyPI Trusted Publishing; create the
   `AES256Afro/homebrew-videokidnapper` tap repo.
2. Bump `__version__`, move CHANGELOG `[Unreleased]` → `[1.3.0]`, `git tag v1.3.0 && git push --tags`.
3. Both workflows fire → `VideoKidnapper.exe` + Inno Setup installer land on the Release.
4. **Verify** the `.exe` boots on a clean Windows VM with no Python (CI only smoke-tests `--help`).

### Phase 1 — Make the binary self-sufficient (bundle FFmpeg) — **M (1–2 days)**

1. Download an **LGPL** FFmpeg build at CI time (per platform).
2. Add `ffmpeg` / `ffprobe` to the PyInstaller `datas`; update the binary resolver to
   check the bundled path first.
3. If one-file startup gets slow with the ~80 MB binary, switch to a `--onedir` build for
   the installer/AppImage/DMG and keep the portable `.exe` slim (external FFmpeg).

### Phase 2 — Linux port (AppImage) — **M (2–3 days)**

AppImage = download, `chmod +x`, double-click. No install, no root, no Python.

1. Add a `build-linux` job on `ubuntu-latest`.
2. PyInstaller `--onedir` build.
3. Wrap with `linuxdeploy` + `appimagetool` (or `python-appimage`) → `VideoKidnapper-x86_64.AppImage`.
4. Bundle LGPL FFmpeg static build.
5. Handle Tk/Tcl data files (the spec already collects customtkinter theme JSON) and the
   `sounddevice` / PortAudio native dep.
6. Attach to the GitHub Release.
7. **Test** on clean Ubuntu + a non-Debian distro (Fedora) — AppImage portability varies with glibc.

*Optional follow-on — Flathub (L, ~1 week):* broader reach + auto-updates, but Flatpak
sandboxing complicates FFmpeg subprocess calls, browser-cookie reads, and file pickers.
Do AppImage first; pursue Flatpak only on demand.

### Phase 3 — macOS port (.app + .dmg) — **M (2–3 days)**

1. Add a `build-macos` job on `macos-latest` (PyInstaller must build on the target OS —
   no cross-compiling a `.app`).
2. `--windowed` build → `VideoKidnapper.app`, wrapped in a `.dmg` (`create-dmg` / `hdiutil`).
3. Bundle LGPL FFmpeg (arm64 + x86_64; universal2 build or two DMGs).
4. **Gatekeeper blocker:** unsigned `.app` is blocked by default ("app is damaged"). Either
   ship unsigned + document the right-click-Open workaround (free, ugly), or join the
   **Apple Developer Program ($99/yr)** → codesign + notarize → clean double-click.

### Phase 4 — Frozen-binary yt-dlp updater — **S–M (1–2 days)**

The pip-based updater can't work inside a PyInstaller bundle (already detected; users are
pointed to the releases page). Better: have the frozen app download the standalone `yt-dlp`
binary into its data dir and prefer it over the bundled module. Closes the "stale
extractor" gap without a full app re-release.

### Phase 5 — MSIX + Microsoft Store (Windows installed path) — **M (2–3 days)**

1. Package the PyInstaller `.exe` into `.msix` (`makeappx` + the Windows SDK, or MSIX Hero
   locally; automate in CI).
2. **Half-day container test:** verify browser-cookie reads and the settings-file write
   work under MSIX virtualization with `runFullTrust`.
3. Register a Microsoft Store individual dev account ($19 one-time); submit the package.
   Microsoft signs it → no SmartScreen, auto-update via App Installer.
4. Keep the portable `.exe` shipping in parallel.

### Code signing summary

- **Windows:** solved for near-free by the Store/MSIX path (Phase 5, $19 one-time).
  Non-Store sideloading still needs an OV/EV cert ($200–400/yr) or Azure Trusted Signing
  (~$10/mo) — only if Store distribution is rejected.
- **macOS:** the $99/yr Apple Developer membership from Phase 3.

---

## 7. Effort summary

| Track | Effort | Calendar (part-time) |
|---|---|---|
| Windows shipped (Phase 0) | S | ~half a day |
| FFmpeg bundling (Phase 1) | M | 1–2 days |
| Linux AppImage (Phase 2) | M | 2–3 days |
| macOS .app/.dmg (Phase 3) | M | 2–3 days |
| Frozen yt-dlp updater (Phase 4) | S–M | 1–2 days |
| MSIX + Store (Phase 5) | M + $19 | 2–3 days |
| **All platforms, no Python, self-sufficient** | | **~10–13 focused days** |

---

*Update this file in the same PR that ships or re-scopes a phase — the same discipline
`ROADMAP.md` and `BLUEPRINT.md` ask for.*
