# Changelog

All notable changes to this project are documented here. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); the project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[1.1.0]: https://github.com/AES256Afro/VideoKidnapper/releases/tag/v1.1.0
[1.0.0]: https://github.com/AES256Afro/VideoKidnapper/releases/tag/v1.0.0
