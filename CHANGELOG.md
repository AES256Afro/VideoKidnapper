# Changelog

All notable changes to this project are documented here. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); the project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.6.0] — 2026-07-09

### Changed

- **One tab does everything.** The separate "Trim Video" and downloader tabs are merged into a single **Kidnap & Trim** studio: load a file, record the screen, or paste a link — then trim, caption, and export in the same place. The two tabs had been carrying identical copies of the editor, which is exactly the duplication that made the app feel confusing. The download bar (link entry, platform chips, cookies, batch queue) is now a strip above the player; a finished download flows straight into the editor. `Ctrl+V` a link from anywhere still routes here.
- **Plain-English description everywhere.** README, the website, the Microsoft Store listing, and the in-app tagline are rewritten around what the app does (download, trim, caption, export) instead of "dark-themed", with no em dashes. Canonical copy, including a ready-to-paste Store description body and one-per-line feature list, lives in `docs/STORE_LISTING.md`; `docs/STORE_UPDATE_GUIDE.md` walks through updating the listing.
- **Fresh screenshots** of the merged UI for the README and website, plus a set of exact 1920×1080 Store screenshots in `assets/store/`.
- **One logo, every size.** All square icons (app window, `.exe`/`.ico`, `.icns`, favicon, AppImage/deb, MSIX tiles) are regenerated from a single master matching the Microsoft Store artwork: the balaclava on the dark brand tile.

### Added

- **macOS build.** `.dmg` installers for Apple Silicon and Intel, built on tag push by `.github/workflows/macos.yml` (PyInstaller `.app` + bundled FFmpeg + `create-dmg`). Unsigned for now — first launch is right-click → Open. See `packaging/macos/README.md`.

## [1.5.1] — 2026-07-07

### Fixed

- **The "Prerequisites Missing" screen no longer traps you in a loop.** Boot detection and the Setup dialog used two different FFmpeg checks — boot ran `ffmpeg -version` as a subprocess (which fails intermittently in a windowed packaged build), while Setup only checked the files exist. So boot showed "missing" while Setup insisted everything was installed, and Install/Relaunch had nothing to do. Both now use the same existence check; the `-version` call is a best-effort probe that can no longer hide a working install. If FFmpeg is present, the app launches straight into the UI.
- **Missing prerequisites now auto-install and continue into the app** — no dead-end landing. A "Setting up VideoKidnapper" screen installs what's missing (FFmpeg download, no admin), streams progress, and drops you into the app when done. FFmpeg needs no restart; a source checkout that had to install Python packages restarts automatically. If the install fails, clear **Open Setup / Retry / Exit** options appear.
- **The Setup dialog's Relaunch button now works.** It was created without a relaunch callback and fell back to `os.execv`, which misbehaves for a packaged `.exe`; it now uses the app's reliable restart path.

## [1.5.0] — 2026-07-03

### Changed

- **The downloader is now the front door.** The URL tab is renamed **Kidnap Social Media Downloader**, moved to the first position, and is the default view on launch — paste a link, download, edit.
- **Ctrl+V is clipboard-aware from any tab.** Pasting a video/GIF link anywhere in the app switches to the Kidnap downloader with the URL filled in and the matching platform chip lit. Non-link clipboards keep their old behavior (an image pastes as an overlay on Trim; plain text lands in the URL entry on the downloader). Single-token http(s)/www links only — sentences, file paths, and multi-line clipboards are never hijacked.
- **Platform chips no longer masquerade as buttons.** The YouTube/Instagram/X/Reddit/Bluesky/Facebook pills never did anything on click but had borders and hover states that said otherwise. They're now honest passive indicators — muted until the pasted URL matches, then lit in the platform's brand color — and the reclaimed space above the URL entry now shows the actual flow: *paste → download → trim, caption & export*.
- **The Setup dialog now shows its work.** Everything missing is pre-selected (installing what's absent is the default; unticking is the opt-out), a plan line spells out exactly what clicking Install will do ("FFmpeg (portable download, no admin), tkinterdnd2 (pip)"), and a new in-app console streams the real script output live — every pip line and FFmpeg download step. When it finishes, the console summarizes what was installed or failed, and the **↻ Relaunch to apply** button lights up and takes focus. The elevated-terminal route remains as an explicit "Advanced" fallback, and it now prints the exact commands it will run into the console first.

### Fixed

- **Setup-installed FFmpeg now survives a restart of the packaged app.** The portable-FFmpeg install destination resolved inside PyInstaller's per-run temp extraction dir for frozen builds, so the binaries vanished on relaunch. Frozen builds now install next to the executable, where the resolver already looks.
- **pip installs from the packaged app fail fast with an explanation** instead of re-invoking the app exe as if it were Python (Python packages are bundled in frozen builds; only FFmpeg can need installing).

## [1.4.1] — 2026-07-02

### Added

- **Microsoft Store / MSIX packaging.** `packaging/msix/` builds `VideoKidnapper.msix` from the same PyInstaller exe (manifest, balaclava Store tiles, `build-msix.ps1`). Store distribution gets Microsoft-signed packages — no SmartScreen warning — for a $19 one-time developer registration. FFmpeg is bundled into the package because the MSIX app container does not inherit PATH. A `videokidnapper` execution alias gives CLI parity with the pip/deb installs. See `packaging/msix/README.md`.
- **`apt-get install videokidnapper`.** Every release now ships `videokidnapper_X.Y.Z_amd64.deb` (same PyInstaller bundle as the AppImage, but `Depends: ffmpeg` instead of bundling it) and publishes it to a signed APT repository served from GitHub Pages ([`AES256Afro/apt`](https://github.com/AES256Afro/apt)). One-time source setup, then updates flow through `apt upgrade`. The deb also installs a launcher-menu entry and icon.

### Fixed

- **FFmpeg now resolves next to the app executable, not just on PATH.** `find_ffmpeg` / `find_ffprobe` check `<exe dir>/assets/ffmpeg/bin` when the app is frozen, so packaged builds that bundle their own FFmpeg work even where PATH isn't propagated (notably inside the MSIX app container, where the activation broker doesn't rebuild PATH from the registry). Regression tests cover the frozen-app lookup.
- **CLI no longer crashes on legacy Windows consoles.** Progress lines containing characters like `→` raised `UnicodeEncodeError` under a cp1252 console (e.g. plain `cmd.exe`, or an attached pipe), aborting the run before export. stdout/stderr are now reconfigured to replace un-encodable characters instead of crashing.

## [1.4.0] — 2026-07-02

### Security

- **Pillow version cap raised (`<12.0` → `<13.0`).** The old upper bound forced installs onto Pillow 11.x, which is affected by two moderate advisories fixed in 12.2.0. Python 3.10+ now resolves a patched Pillow (3.9 stays on 11.x — Pillow 12 dropped 3.9 support); the shipped `.exe` and AppImage bundle the patched version.

### Added

- **Brand identity: the balaclava logo.** A solid ski-mask robber head as a flat single-color pictogram (eye holes and mouth are true cutouts, so the mark works on any background). Master SVGs live in `assets/branding/`; a multi-size `icon.ico` + `icon.png` ship inside the package. The icon now shows on the app window and taskbar, the `VideoKidnapper.exe` file and its Start Menu shortcut, the Inno Setup wizard, the Programs & Features entry, and the README header.
- **Linux AppImage.** `VideoKidnapper-x86_64.AppImage` — download, `chmod +x`, run. PyInstaller one-dir bundle + FFmpeg (BtbN GPL build, source linked in the release notes) squashed by appimagetool; `AppRun` prepends the bundled FFmpeg to `PATH` so the existing lookup finds it unchanged. Built on ubuntu-22.04 for a glibc 2.35 floor: Ubuntu 22.04+, Debian 12+, Fedora 36+, Bazzite, SteamOS 3+. New workflow `appimage.yml` attaches it to every release; manual dispatch builds test artifacts from any branch.

## [1.3.0] — 2026-07-02

### Added

- **Text outline and shadow.** Two new per-layer toggles on every text layer:
  - **Outline** — drawtext `borderw=2:bordercolor=black`, the classic white-text-black-outline social caption look. Imported layer dicts with other widths (SRT round-trips, plugins) keep their width.
  - **Shadow** — drawtext `shadowx=2:shadowy=2:shadowcolor=black@0.7`.
  Both render identically in the live preview (PIL `stroke_width` for outline, offset translucent draw for shadow) and in the export. Off by default — pre-existing layers produce byte-identical filter strings.
- **Bold / italic text.** B / I checkboxes per layer. The font resolver now finds style-variant files next to the regular face (`arialbd.ttf`, `ariali.ttf`, `georgiab.ttf`, `trebucit.ttf`, `calibriz.ttf`, …) with graceful fallback: missing Bold Italic tries Bold, then Italic, then regular — a missing variant can never fail an export.
- **Multiline captions.** The text input is now a wrapping 2-line textbox; embedded newlines render as real line breaks in both the preview and the export (drawtext renders `\n` natively). `\r\n` / `\r` are normalised so SRT files and Windows clipboard text can't smuggle tofu glyphs.
- **"Caption" style preset** — white text, 2px black outline, no box, bottom center. The social-standard look in one click, alongside Subtitle / Title / Watermark / Custom.
- **Blurred-background aspect fill.** A new **Fill** dropdown next to Aspect in Export Options: **Crop** (the historical center-crop) or **Blur fill**, which fits the whole frame over a scaled, blurred copy of itself — the standard Shorts / Reels / TikTok look for 16:9 → 9:16 conversion, with no pixels lost and no black bars. Compiles to a `split / scale / boxblur / overlay` filtergraph slotted into the same chain position as the aspect crop; blur radius scales with the canvas so 480p and 4K look alike. Persisted via settings schema v6 (additive migration from v5); the default reproduces the historical crop exactly.
- **`_build_aspect_fill_blur`** in `core/ffmpeg/filters.py` — pure builder with the same defer-to-explicit-crop and invalid-input no-op semantics as `_build_aspect_crop`. Canvas dimensions are forced even for yuv420p.
- **GIF palette options: dither, palette stats mode, loop count.** New "GIF" row in Export Options with three dropdowns, all persisted across launches (settings schema v5, additive migration from v4):
  - **Dither** — Bayer (the previous hardcoded default: patterned retro look, smaller files), Floyd-Steinberg (smoother gradients, the GIPHY look), Sierra (middle ground), or None (flat-color sources like screen recordings compress dramatically better without dithering).
  - **Palette** — Full frame (previous behavior) or Motion (`palettegen=stats_mode=diff`), which weights the palette toward pixels that change between frames — a visible quality win for clips with static backgrounds.
  - **Loop** — Forever (previous behavior), Once, or 2× / 3× / 5×.
  Defaults reproduce the old hardcoded pipeline exactly, so existing users' GIFs are byte-identical until they touch the new controls.
- **`_build_palettegen_filter` / `_build_paletteuse_filter` / `_gif_loop_flag`** in `core/ffmpeg/filters.py` — pure builders with clamping and unknown-value fallbacks, so a hand-edited settings file can't produce a command ffmpeg rejects. `frames_to_gif` grew an optional `options=` param so the screen-record path can use the same knobs.
- **⟳ Update yt-dlp button** on the URL tab's cookies row. A stale extractor is the most common cause of "this video won't download" — the fix is now one click: upgrades via pip on a worker thread and reports the old/new version (with a restart hint when the old module is already loaded). Bundled `.exe` builds get a clear pointer to the releases page instead, since pip can't install into a PyInstaller bundle.
- **Outdated-extractor hint on failures.** When a download error matches known stale-extractor signatures ("Unable to extract...", "Unsupported URL", HTTP 403, nsig failures), the error line appends "yt-dlp may be outdated; try ⟳ Update yt-dlp" so users aren't left guessing.
- **`videokidnapper/utils/ytdlp_update.py`** — version probe (installed vs. PyPI), date-version comparison, frozen-build detection, and the extractor-failure heuristic. All network paths take short timeouts and never raise.
- **Cookies file support in the UI.** The "Cookies from" dropdown grew a **Cookies file…** entry that opens a file picker for a `cookies.txt` export (from extensions like "Get cookies.txt LOCALLY"). The backend always supported cookie files; the UI just never exposed them. The chosen file shows as `file: <name>` in the dropdown, picking a browser or "(no cookies)" clears it, and cancelling the picker reverts cleanly. This is the reliable path on Windows now that Chrome's App-Bound Encryption blocks `--cookies-from-browser`.
- **Drag image overlays anywhere on the frame.** Click and drag any image, logo, sticker, or **animated GIF** overlay on the Trim preview — it moves in lockstep under the cursor and the exported video / GIF renders at the dragged position, not the anchor. Picking a new entry from the Position dropdown (Top Left, Center, …) snaps the overlay back to the anchor so the dropdown label is always truthful. Works the same way text-layer drag already does.
- **Explicit `x` / `y` in the image-layer data.** When either axis is unset (sentinel `-1`), the preview and ffmpeg backend fall back to the anchor; when both are set, they win as source-video pixel coords. `_overlay_position_expr` grew optional `x=` / `y=` params that clamp negatives to 0 so a drag near the edge can't produce an off-canvas overlay.
- **`ImageLayersPanel.set_layer_position(index, x, y)`** and **`VideoPlayer.set_image_position_callback(cb)`** — twin public hooks that mirror the text-drag pair, so any future drag source (pen, gesture, plugin) can drive image positioning without patching widget internals.
- **Paste an image into the video.** `Ctrl+V` on the Trim tab now grabs whatever image is on the clipboard — a screenshot, a "Copy image" from a browser, or a PNG / JPG / WebP / GIF / BMP file copied in Explorer / Finder — and drops it in as a new image overlay. Bitmap data is saved as PNG into the app temp dir; file-path clipboards use the file as-is (so animated GIFs keep their animation). The Image Overlays panel also grows a **📋 Paste from clipboard** button for discoverability, wired to the same path. The URL tab's existing `Ctrl+V` (paste URL text) is unaffected — the shortcut dispatcher routes by active tab.
- **`videokidnapper/utils/clipboard_image.py`** — pure helper `grab_clipboard_image(temp_dir=None)` that never raises: PIL missing, clipboard unreachable (headless Linux without xclip / wl-paste), write-permission denied, non-image file paths — all resolve to `None` so the UI can uniformly toast "no image in clipboard."
- **`ImageLayersPanel.add_layer_from_path(path)`** — public hook so both the clipboard path and any future drag-drop route can pre-populate a new layer's image path without touching widget internals.

### Fixed

- **Export-pipeline bughunt (nine verified bugs, all with regression tests where unit-testable).** An infinite loop in the audio-speed filter builder on non-positive speeds (hung the encode thread — speed is now clamped to 0.1–100×); a drawtext position without a colon aborting the whole encode instead of falling back to bottom-center; both concat loops busy-waiting at 100% CPU without draining ffmpeg's stderr (a chatty encode could fill the pipe buffer and deadlock — replaced with a stderr-draining thread and `wait(timeout=)`, plus the missing `-loglevel error` on `concat_clips`); GIF exports with image overlays double-applying the `eq=` color grade (baked into the intermediate MP4, then re-applied on the GIF pass); a filtergraph ending in a dangling `;` (all overlay layers with invalid timing) being rejected by ffmpeg instead of falling back to `-vf`; `get_video_info()` crashing with a naked `ValueError` on "N/A" durations (image/HLS inputs) instead of routing through the `ProbeError` funnel; and a console-window flash on probe calls under Windows.
- **Playback:** starting playback no longer fires a spurious `on_finished("stopped")` callback to the UI the instant it begins, and the sounddevice output stream is torn down at natural end-of-clip instead of leaking.
- **Stale thumbnail strip:** the cache key now includes duration and thumb count, so regenerating the strip for a different trim range can't return thumbnails from the previous range.
- **Downloads now retry transient network failures and resume partial files.** `download_video` wraps yt-dlp in a bounded retry loop (3 attempts, 2s/4s backoff) that triggers only on transient signatures — timeouts, connection resets, HTTP 429/5xx, DNS hiccups — never on permanent failures like private videos or unsupported URLs. `continuedl` is enabled so each retry resumes the partial download instead of starting over; a mid-backoff cancel takes effect immediately.
- **Raw "Could not copy Chrome cookie database" errors replaced with an actionable message.** Cookie-read failures (database locked by a running browser, DPAPI / App-Bound decryption failures) now explain the three escape routes up front: close the browser fully and retry, switch the dropdown to firefox, or use a cookies file. The URL tab's error line also shows up to 160 characters (was 80) so hints like this survive truncation.
- **Preview rendered translucent text elements as opaque.** PIL's `ImageDraw` overwrites pixels rather than alpha-blending, so the subtitle background box (`black@0.6`) and the Watermark preset's `white@0.5` text previewed fully opaque while exporting translucent — a real preview/export divergence. Text layers now render per-layer on a transparent scratch image that is alpha-composited onto the frame, so preview translucency finally matches the export.
- **Race-prone GIF palette temp files.** `trim_to_gif` / `frames_to_gif` reserved palette paths with the deprecated `tempfile.mktemp`, which only reserves a *name* — two concurrent GIF exports (reachable since the Batch Export tab) could collide on the same palette file. Now uses `mkstemp` (atomic creation) and `try/finally` cleanup, so a failed or cancelled encode can no longer leave orphan palette PNGs or intermediate MP4s behind.
- **Theme toggle felt broken.** Clicking the ☀ / ☾ chip in the header used to silently save the new theme and emit a status-bar toast with "restart to apply" — easy to miss, and the app didn't visibly re-theme, so the button felt dead. Now clicking pops a small "Theme set to X. Restart now?" dialog with **Restart now** / **Later**. Picking Restart cleanly relaunches the process (dev `python main.py`, `python -m videokidnapper`, and PyInstaller `.exe` all handled). The button icon also flips immediately on click — visual confirmation the preference saved, even if you pick Later.

### Tests

- 416 tests, including new regression coverage for the export-pipeline and playback fixes above.

## [1.2.0] — 2026-04-18

### Added

- **Batch Export polish: right-click, per-row platform override, persistence.** Three deferred follow-ups from the Batch Export tab in one pass.
  - **Right-click context menu** on every batch row — Reveal output in Explorer (disabled until the job finishes), Open source folder, Reset status to queued, Remove from queue. The existing `✕` button stays as a one-click remove; the menu adds discoverability for everything else.
  - **Per-row platform override.** Each row now has its own Platform dropdown alongside the status. Default **Inherit** uses the batch-wide Quality + aspect; any other choice (YouTube Shorts, Instagram Post, Discord 8 MB, …) flips quality + aspect just for that file. Format stays batch-wide so the pre-displayed output path never becomes a lie.
  - **Persisted queue.** The queue, per-row overrides, and terminal statuses (done / failed / cancelled) now survive app restarts. A partial run that gets force-quit mid-encode comes back with the still-running row normalised to queued (so it re-runs cleanly) and everything downstream still queued — nothing is silently lost.
- **Settings schema v4** (additive migration from v3) — new `batch_jobs` key holds the serialised queue. Empty by default, so existing users see no behaviour change until they use the Batch Export tab.
- **`BatchJob.to_dict` / `BatchJob.from_dict`** — round-trip serialisation with two guards baked in: required-path validation (a malformed row raises `ValueError` so restore can drop it instead of crashing the tab), and in-flight status normalisation (a persisted `processing` status loads back as `queued`, since "processing at shutdown" is always a lie).
- **`extend_batch_jobs()`** in `utils/batch.py` — re-entrant planner that preserves per-row state (status, error, `platform_override`) on rows already in the queue, while still deduplicating and collision-checking new inputs. `plan_batch_jobs` is now a thin wrapper over it.
- **⎆ Batch Export tab.** New tab that targets the "I already have 10 local files and want to recompress / reformat / resize them all with the same settings" workflow — podcasts, stream exports, lecture recordings. Add files via the button or drag-drop, pick shared Quality + Export Options (aspect, speed, color grade, HW encoder all propagate from the Trim tab's settings), hit Start. Jobs run sequentially in a background thread with per-row live status (queued / running + %  / done / failed / cancelled), a Stop button that interrupts cleanly, and an empty-state prompt when the queue is cleared. Output filenames preserve the source stem (`podcast_ep5.mov` → `podcast_ep5_batch.mp4`) with numeric suffixes on collision.
- **`videokidnapper/utils/batch.py`** — pure helpers (`plan_batch_jobs`, `plan_output_path`, `summarise`, `BatchJob` dataclass, status constants). Fully unit-tested without a Tk root so planner regressions can't hide behind widget code.
- **Keyboard shortcuts overlay (`?` key).** Press `?` anywhere in the app — or click the new `⌨` header chip — to open a categorized cheat sheet listing every advertised binding (playback, trim, edit, file & export, help). The binding registry (`videokidnapper/ui/shortcuts_dialog.py`) is a single source of truth; a drift-check test cross-references it against the actual `bind_all` calls in `app.py` so the overlay never lies about what the app supports. Esc or a second `?` closes the dialog. `?` inside a text entry still types a literal `?`, so captions aren't affected.
- **`⌨` header chip** — discoverable second entry-point alongside the existing Setup and Theme chips.
- **Platform export presets.** New **Platform** dropdown in the Trim tab's export row with 13 entries — YouTube 1080p / Shorts, Instagram Reel / Post / Story, TikTok, Twitter / X, Bluesky, Discord 8 MB / 25 MB, Slack GIF, Web Embed, plus **Custom** (no-op). Picking a preset snaps Quality + Format + aspect ratio in one click; editing any of those three fields afterwards reverts the label to Custom so the dropdown never claims a preset the user has deviated from. Preset choice persists across launches via the new `platform_preset` settings key.
- **`videokidnapper/ui/platform_presets.py`** — single source of truth for the preset registry, consumed by the trim tab dropdown and validated by tests that every entry resolves to valid Quality / Format / aspect values.
- **`ExportOptionsPanel.set_aspect(value)`** — public hook so the Platform dropdown can drive the aspect ratio without forcing users to open the collapsed Export Options panel.
- **Undo / redo (Ctrl+Z / Ctrl+Y / Ctrl+Shift+Z)** across the whole editor — text-layer add / remove / reorder / edit, crop rectangle, trim range, queued ranges. 50-step history; debounced 350ms so a typed sentence collapses to one undo step instead of one-per-keystroke. Ctrl+Z inside a text entry still performs field-level undo (Tk handles that natively).
- **Thumbnail strip** above the waveform — 32 downscaled frames extracted in a background thread, rendered as a scrubbable strip. Click any thumb to move the trim start; the current range is outlined with an accent border and dimmed outside. Thumbs share the same LRU cache as the main preview so a second load of the same video is instant.
- **Snap-to-guides when dragging text layers** — the dragged layer now snaps to frame center-X / center-Y, the padded frame edges (same 20-px margin the Top-Left / Bottom-Right presets use), and to every edge + center of every other text layer. Snap threshold is 8 source-pixels; dashed accent guide lines render while a snap is active and clear on release. Axes snap independently, so a drag can align horizontally without locking vertically.
- **Color grade controls** in Export Options — four sliders (**Brightness**, **Contrast**, **Saturation**, **Gamma**) compile to an ffmpeg `eq=` filter that runs after the geometric ops (crop/rotate) and before speed/drawtext. Out-of-range values are clamped before the filter string is built so a hand-edited settings file can't produce a command ffmpeg rejects. A **Reset** button snaps all four back to neutral. Neutral values (all at default within 0.001) compile to no filter at all — no per-pixel pass on the "no color tweak" path.
- **Transitions between queued ranges.** Multi-range + Concat now supports four options instead of just cut: **Cut** (existing fast lossless path), **Crossfade** (xfade `dissolve`), **Fade to black** (xfade `fadeblack`), **Fade to white** (xfade `fadewhite`). Transition duration picker: 0.25s / 0.5s / 1s / 1.5s. Elevates multi-range trimming from "export N files + stitch" to "make a compilation".
- **`concat_clips_with_transition()`** in `ffmpeg_backend.py` — drop-in super-set of the existing `concat_clips`. `transition="cut"` preserves the lossless concat-demuxer path; anything else builds a `filter_complex` with `xfade` for video + chained `acrossfade` for audio.
- **Settings schema v3** (additive migration from v2) — persists color-grade slider state (`color_brightness`, `color_contrast`, `color_saturation`, `color_gamma`) and concat-transition settings (`concat_transition`, `concat_transition_duration`).
- **Plugin system.** Third-party plugins can now extend VideoKidnapper via Python's standard `entry_points` mechanism. A plugin is a regular pip-installable package that declares itself under the `videokidnapper.plugins` entry-point group; VideoKidnapper discovers it at startup, instantiates the class, and calls `on_app_ready(app)`. From that hook a plugin can call `app.register_tab(display_name, factory, glyph="◆")` to add new tabs, log to `app.debug_tab`, post to `app.status_bar`, or read any documented app state. One broken plugin never kills the app — load-time and `on_app_ready` exceptions are captured and reported in the Debug tab. Plugins may also declare `min_app_version` / `max_app_version` and incompatible plugins are skipped with a clear reason.
- **`videokidnapper.plugins` subpackage** — `Plugin` base class, entry-point-based `discover_plugins()` loader exposed via the package root.
- **`app.register_tab(display_name, factory, glyph=...)`** — stable plugin API for adding a tab.
- **`app.plugins`** — list of `DiscoveredPlugin` namedtuples for introspection.
- **Example plugin** at `examples/plugins/videokidnapper_hello/` + developer docs at `docs/PLUGINS.md`. Plugins are free to adopt any license (MIT, GPL, proprietary) — the entry-point mechanism is packaging-level, not source-level, so Apache-2.0 doesn't infect.
- **Real-time in-app video + audio playback.** The Play button now decodes the video through a persistent `imageio-ffmpeg` subprocess and streams the audio track as PCM through `sounddevice`, synced to an audio-mastered clock. Replaces the previous 8-fps frame-scrub loop that had no sound (which is why the "Play in System Player" workaround existed). Optional deps — the core install is untouched, and users who skip the extras automatically get the old scrub behavior as a graceful fallback.
- **`videokidnapper/core/playback.py`** — new module with `AudioVideoPlayer` (threaded audio + video decode with audio-as-master sync), `AudioClock` (unit-testable sync math isolated from I/O), and `is_available()` (checks the three optional deps: `imageio-ffmpeg`, `sounddevice`, `numpy`). Silent clips fall back to a `time.monotonic()` clock so video never stalls waiting for audio that doesn't exist.
- **PyPI package.** `pip install videokidnapper` (core) or `pip install "videokidnapper[dnd]"` (+ drag-and-drop) now works. Installs a `videokidnapper` console script that launches the GUI (or the CLI with any flag). FFmpeg is still an external prereq — the in-app **⚙ Setup** dialog handles portable install on Windows.
- **Standalone Windows `.exe`** — tag-push builds a one-file PyInstaller executable via a new `.github/workflows/installer.yml`. Users download `VideoKidnapper.exe` from the release page, double-click, done — no Python install required. FFmpeg is still an external prereq; the in-app Setup dialog handles it on first run.
- **`packaging/videokidnapper.spec`** — PyInstaller spec file with `collect_all` calls for `customtkinter` and `tkinterdnd2` (so their package data — theme JSON, native TCL resources — is bundled correctly), `yt_dlp.extractor` as an explicit hidden import, and `matplotlib` / `pandas` / `IPython` excludes to keep the binary under ~40 MB.
- **Manual `workflow_dispatch` trigger** on the installer workflow — maintainers can rebuild the installer for an existing tag without re-tagging (useful after a PyInstaller version bump).
- **Proper Windows installer via Inno Setup.** Tag pushes now build **both** `VideoKidnapper.exe` (the portable PyInstaller binary) **and** `VideoKidnapper-Setup-X.Y.Z.exe` (an Inno Setup 6.x wizard that adds a Start Menu shortcut, registers in Programs & Features, and handles uninstall cleanly). The installer defaults to per-user install (no admin prompt) with an opt-in machine-wide option; desktop shortcut is off by default; user settings (`~/.videokidnapper_settings.json`) survive uninstall so a reinstall picks up where the user left off. Both files attach to the GitHub Release; the portable is still offered for users who want a no-install download.
- **`packaging/inno-setup/videokidnapper.iss`** — the Inno Setup script. Uses a permanent `AppId` GUID so upgrades detect previous installs correctly. `x64compatible` architecture restriction (Inno Setup 6.x+).
- **🗣 Auto-captions via Whisper.** New button in the Trim tab runs [faster-whisper](https://github.com/guillaumekln/faster-whisper) over the current trim range and imports the result through the existing SRT → text-layers pipeline. Captioned clips are ready to export instantly. Model size is pickable (tiny / base / small / medium / large) in a small dialog.
- **`videokidnapper/core/whisper_captions.py`** — pure module: audio extraction via ffmpeg at the correct 16 kHz mono s16 format, segment → SRT-dict conversion (tested independently of the model), and a threaded transcribe entry point with progress + cancellation. Auto-captions feed the same layer importer as `parse_srt_file`, so the downstream UI code is unchanged.
- **Optional dep: `faster-whisper`.** Added to `requirements.txt` under a commented "Optional" block. The button checks `is_available()` at click time and shows a `pip install faster-whisper` hint when missing — nothing else in the app changes.
- **Image / logo overlay track.** New collapsible **Image Overlays** panel on the Trim tab. Each layer carries a file path (PNG / JPG / WebP / GIF / BMP), a position anchor (7 presets matching the text anchors), a scale slider (5–100% of image width), an opacity slider (0–100%), and a start/end timing slider. Great for watermarks, reaction stickers, brand bugs. Mirrors `TextLayersPanel`'s pattern so add/remove/timing feel consistent.
- **`_build_image_overlay_chain()`** in `ffmpeg_backend.py` — produces the per-layer `format → scale → colorchannelmixer → overlay` chain as a filter_complex string. Clamps out-of-range inputs (scale/opacity/timing) so corrupt settings can't break the encode. Zero-duration layers are silently dropped.
- **`trim_to_video` now accepts `image_layers=`.** When any are present, the command switches from `-vf <chain>` to `-filter_complex [0:v]<chain>[vbase];…[ov]overlay=…` with one `-loop 1 -i <image>` per layer. Existing encodes with no image overlays are unchanged.
- **Integration test that actually runs ffmpeg** (`tests/test_integration_ffmpeg.py`). Builds a tiny 1-second synthetic source via lavfi (`color` + `sine`), probes it with `get_video_info`, then runs the full `trim_to_video` path with a text overlay and encoder pinned to libx264. Catches wiring regressions — argument ordering, stream mapping, filter-graph composition — that the pure-function unit tests can't see. Skips automatically when ffmpeg isn't on PATH; CI installs it (Ubuntu: apt, Windows: choco) so it always runs there.
- **Type hints** on the pure-function utility modules — `utils/time_format.py`, `utils/ffmpeg_escape.py`, `utils/file_naming.py`, `utils/size_estimator.py`. Every function that's imported by more than one caller now has a typed signature. Makes the API intent legible without an mypy pass.
- **mypy in CI (opt-in allowlist).** New `mypy.ini` at repo root uses `strict = true` as the default but opts every module out via `ignore_errors = true`, then overrides specific typed modules back into strict mode. Currently typed: `config.PRESETS` (TypedDict), `utils/time_format`, `utils/ffmpeg_escape`, `utils/file_naming`, `utils/size_estimator`, `utils/undo`, `utils/snap`. New modules inherit the strict default. `mypy` is a separate CI job from `ruff` and `test` so a type-check regression doesn't block other signals.
- **`config.Preset` TypedDict** — replaces the bare `Dict[str, Dict[str, object]]` that made `preset["width"]` un-indexable. Now narrows to `Optional[int]` at every call site.
- **Full type signatures** on `utils/undo.py` (every method, including the generic `Snapshot = Any` alias) and `utils/snap.py` (including the `BBox` tuple type alias). Both pass `mypy --strict`.
- **`.github/workflows/release.yml`** — tag push matching `v*.*.*` builds an sdist + wheel, publishes to PyPI via Trusted Publishing (OIDC — no API token in repo secrets), and attaches the same artifacts to the GitHub Release. Tag→version mismatch fails the build before publish, so a mis-tagged release can't ship.
- **`--version` CLI flag** — `videokidnapper --version` prints the installed version.
- **`ProbeError` exception** in `ffmpeg_backend.py` — narrow, catchable type for ffprobe failures that still deserve user-facing surfacing.
- **`keyboard_paste_url()` on `UrlTab`** — dispatched by the new Ctrl+V binding.
- **`_WRITE_LOCK` in `utils/settings.py`** — module-level lock guarding every read-modify-write path.

### Changed

- **Status-bar hint** now mentions Ctrl+Z / Ctrl+Y alongside the existing shortcuts.
- **`VideoPlayer.play()`** branches at call time: if `playback.is_available()` the threaded A/V player runs; otherwise the original scrub loop does. `stop()` handles both modes uniformly so keyboard nudges, slider moves, and the Stop button work identically regardless of which path started playback.
- **`requirements.txt`** documents the three optional playback deps under a commented "Optional" block; core dependency list unchanged.
- **README** Highlights reflect the real-time A/V playback; "Play in System Player" stays listed as a fallback rather than the only audio-sync option.
- **`videokidnapper/__init__.py` is now the single source of truth for version.** `config.APP_VERSION` re-exports `__version__`, and `pyproject.toml` uses `tool.setuptools.dynamic` to read the same attribute — one bump, everything agrees.
- **`main()` moved from repo-root `main.py` into `videokidnapper/cli.py`** so it's importable as a package attribute (required by the console-script entry point). Root `main.py` stays as a thin shim — `python main.py …` from a clone still works unchanged.
- **README install section** documents the PyPI path as option A and keeps the clone-based path as option B.
- **CI installs ffmpeg** on both Ubuntu and Windows runners so the new integration test has a real binary to invoke. Previously CI relied on unit tests that mocked `subprocess.run` — this fills the coverage gap.

### Fixed

- **ffprobe crash on bad / truncated files.** `get_video_info` used to call `json.loads(result.stdout)` with no try/except and no return-code check — a corrupt file, a killed ffprobe, or a missing binary raised an uncaught `JSONDecodeError` / `FileNotFoundError` into the Tk event loop. Now wrapped in a new `ProbeError` with a human-readable reason for every failure mode (bad output, non-zero exit, timeout, binary not on PATH); callers already catch the old generic-Exception path so this is wire-compatible.
- **UI freeze on stalled URLs.** `get_video_info_from_url` invoked `yt_dlp.YoutubeDL.extract_info` with no timeout — a stalled CDN could hang the caller indefinitely. Now runs on a worker thread with a soft 20-second timeout (caller-overridable), returning `{"error": "timed out after Ns"}` instead of hanging. Also sets yt-dlp's own `socket_timeout` to half the outer timeout so individual network reads don't stretch past our bound.
- **Settings file corruption under concurrent writes.** `~/.videokidnapper_settings.json` was written with a plain `open(..., "w") + json.dump` — two exports finishing simultaneously could interleave read-modify-write cycles and one would clobber the other's update (regularly observed as "lost history entry after batch download"). The write path now holds an in-process lock across the full read-modify-write and writes via tempfile + `os.replace` for atomicity at the filesystem level. `add_history_entry` is locked too so batch-download history survives concurrent exports.
- **Ctrl+V paste-URL shortcut was documented but not wired.** README + URL-tab placeholder told users Ctrl+V pastes into the URL field, but no binding existed. Now actually works: Ctrl+V outside of an entry pastes the clipboard into the URL entry and triggers the platform-detect chip; Ctrl+V inside an entry keeps native text-field paste (via the existing entry-focus guard).
- **Version drift:** `videokidnapper/__init__.py` had `__version__ = "1.0.0"` while `config.APP_VERSION` was `"1.1.0"`. Both now resolve to `"1.1.0"`.

### Notes

- **Standalone Windows `.exe` is not yet a full installer.** Tag-push produces a one-file PyInstaller binary via `.github/workflows/installer.yml` — 80% solution. A true installer (Inno Setup / WiX with Start Menu entries and uninstall) is a follow-up PR.
- **Code signing** is intentionally left out. Unsigned `.exe`s trigger SmartScreen warnings; addressing that needs an EV cert, which costs money and maintainer setup. Follow-up once the release cadence is established.
- **faster-whisper over openai-whisper:** ~4× faster CPU inference (CTranslate2 backend), no torch / CUDA requirement, same model quality. MIT licensed. Models download on first use into `~/.cache/huggingface`.
- **Auto-captions scope:** transcription only. Translation, speaker diarization, and word-level timestamps are post-MVP.
- **Image overlays: MP4 export only in this PR.** GIF pipeline goes through `palettegen`/`paletteuse` and plumbing filter_complex through that path is more involved than it's worth for the MVP. A follow-up can add GIF support.
- **Image overlays: no live preview yet.** The overlay appears in the exported file; rendering it on the frame-scrub preview is a separate PR.
- **Image overlays MVP: 7 preset anchors, no custom drag.** Drag-to-position is a natural follow-up that would reuse the text-layer drag machinery.

### Changed

- **Image overlays now live-preview** on the scrub canvas. ``VideoPlayer`` grew a ``set_image_layers_provider`` hook (mirrors ``set_text_layers_provider``) and a ``_apply_image_overlay`` pass that composites PNGs onto the source-sized frame using PIL's ``alpha_composite``. Loaded files are memoized by path so scrubbing through frames doesn't re-read from disk. Ordering matches export: image overlays render on top of text overlays.
- **Image overlays now work for GIF export.** ``trim_to_gif`` accepts ``image_layers=``; when any are present, it encodes an intermediate MP4 (via ``trim_to_video``, which already threads filter_complex) and then palette-passes that. Costs one extra libx264 encode but keeps the palettegen/paletteuse plumbing untouched. Quality loss is dominated by the palette reduction anyway.

## [1.1.0] — 2026-04-18

### Changed

- **License: relicensed from GPL-3.0 to Apache License 2.0.** Releases tagged at or before `v1.0.0` remain available under GPL-3.0; Apache-2.0 applies to `v1.1.0` and every later commit on `main`. Motivation: permissive licensing is better aligned with the project's goals of broad adoption, corporate-friendly use, and the option of layering proprietary services or premium features on top in the future without copyleft friction.

### Fixed

- **Drag-to-position drift under preset scaling.** The video filter chain was reordered from `crop → rotate → scale → speed → drawtext` to `aspect-crop → crop → rotate → speed → drawtext → scale`, so custom text positions (and fontsize) are now interpreted in source-frame pixels and render at exactly the location the preview shows. Previously, a drag to `(960, 540)` on a 1080p source with the Medium preset landed at pixel `960` of a 720-wide export — well past the right edge.

### Added

- **Click-and-drag text positioning** on the preview canvas. Hover a text layer to see a move cursor, drag to reposition. A new **Custom (drag)** entry in the position dropdown activates automatically when you drag; picking any preset snaps the layer back to that anchor.

## [1.0.0] — 2026-04-18

First public release. The overhaul that turned the project from a YouTube-only GIF maker into a multi-platform clip studio.

### Added

- **Multi-platform URL downloads** — YouTube, Instagram, Bluesky, Twitter/X, Reddit, Facebook via yt-dlp with platform-aware format selectors and cookies-from-browser for private content.
- **Share-to-platform panel** in the Export dialog — copies the exported file to the clipboard and opens the platform's compose page, prefilling the caption on X, Reddit, and Facebook.
- **Setup dialog** — feature-driven prerequisites checklist with auto-install for FFmpeg portable + pip packages, plus an elevated-terminal fallback that opens PowerShell / Terminal / gnome-terminal with the right install commands.
- **Screen recording** — `mss`-based capture that drops the recording straight into the trim workflow.
- **Batch URL queue** — paste many URLs, download sequentially, pick one to edit.
- **Multi-range trimming** — queue N clips, export individually or concatenate via ffmpeg's concat demuxer.
- **SRT / VTT import** — auto-populates time-synced text layers from a subtitle file.
- **Crop overlay** — click-drag on the preview canvas, clamped to video bounds, cleared on new video load.
- **Aspect presets** — 1:1, 9:16, 16:9, 4:5, 3:4 via center-crop.
- **Hardware encoder auto-probe** — NVENC, QSV, VideoToolbox, AMF detected and tested with a micro-encode; falls back to libx264 when the probe fails (covers "NVENC listed but no NVIDIA GPU" case).
- **Live waveform** above the timeline with selection highlight.
- **Live text-layer preview** on the canvas — matches ffmpeg's export proportionally (text rendered at source resolution, then the whole composite resized).
- **History tab** — most recent 25 exports with Open / Reveal / size.
- **Play in System Player** — audio-synced playback in the default OS player.
- **Drag-and-drop** video files onto the preview (requires `tkinterdnd2`).
- **Keyboard shortcuts** — Space / K play, J / L ±1s, I / O mark in-out, Ctrl+E export, Ctrl+O open.
- **CLI mode** — `python main.py --url … --start 10 --end 25 --format GIF`.
- **Light + dark themes**, GitHub update check, auto-update chip in header, global exception handler that routes uncaught errors into the Debug tab.
- **Text layer reorder / duplicate / fade / custom color picker**.
- **Rough output size estimate** next to the Export button.
- **Settings persistence** with JSON schema migration.
- **Debug tab** with color-coded INFO / WARN / ERROR levels and ffmpeg stderr capture.
- Project docs: README with screenshots of every tab, CONTRIBUTING.md, SECURITY.md, NOTICE.md.
- Repo infra: GitHub Actions CI (Ubuntu + Windows × Python 3.11 / 3.12 + Ruff), Dependabot, issue and PR templates, maintainer setup checklist.

### Changed

- Tabs (Trim + URL Download) are now `CTkScrollableFrame`-based so the Export button never clips on small windows.
- Minimum window size lowered from 800×600 to 680×480.
- Collapsible panels (Text Layers, Queued Ranges, Export Options, Batch Download) auto-collapse when empty, auto-expand on first content, and remember manual collapses.
- Preview frame cache is now an LRU capped at 240 entries — no more unbounded growth during long sessions.
- Full design-token rewrite — every widget reads from `ui/theme.py` so dark/light switching is a config change, not a repaint.

### Security

- **drawtext / filter-graph escaping** — user text, filenames, and font paths all flow through `utils/ffmpeg_escape.py`. Closes a filter-graph injection path where special characters (`:`, `\`, `;`, `[`, `]`, `'`, etc.) could break out of the filter spec.
- **Crop rect clamping** — out-of-bounds rects now return no filter instead of crashing ffmpeg.
- **Global exception handler** keeps the app alive on uncaught errors and surfaces the traceback in the Debug tab rather than killing the event loop silently.
- **Settings schema migration** tracks a `_version` key so future key renames don't corrupt existing user preferences.

### Fixed

- Export failures no longer disappear silently — ffmpeg's stderr tail is logged to the Debug tab with the real error message.
- Stale crop rect from a previous video no longer applies to the next load.
- `tkinterdnd2` integration no longer causes infinite recursion during Tk root init.
- `python main.py --help` no longer crashes (any argv now routes to argparse, bare launch opens the GUI).
- GIF files can now be dragged in as input; supported extensions extended to `.m4v / .mpeg / .mpg / .ts / .mts / .3gp`.
- Preview text size matches export output regardless of source resolution or preset scaling.

### Tests

- 124 tests covering URL platform detection, share-intent URL construction, ffmpeg filter math (crop clamping, aspect-crop, fade-alpha expression, hardware encoder picking and probing), settings persistence + schema migration, SRT parser, size estimator, LRU cache, and the DnD payload parser.

[1.6.0]: https://github.com/AES256Afro/VideoKidnapper/releases/tag/v1.6.0
[1.5.1]: https://github.com/AES256Afro/VideoKidnapper/releases/tag/v1.5.1
[1.5.0]: https://github.com/AES256Afro/VideoKidnapper/releases/tag/v1.5.0
[1.4.1]: https://github.com/AES256Afro/VideoKidnapper/releases/tag/v1.4.1
[1.4.0]: https://github.com/AES256Afro/VideoKidnapper/releases/tag/v1.4.0
[1.3.0]: https://github.com/AES256Afro/VideoKidnapper/releases/tag/v1.3.0
[1.2.0]: https://github.com/AES256Afro/VideoKidnapper/releases/tag/v1.2.0
[1.1.0]: https://github.com/AES256Afro/VideoKidnapper/releases/tag/v1.1.0
[1.0.0]: https://github.com/AES256Afro/VideoKidnapper/releases/tag/v1.0.0
