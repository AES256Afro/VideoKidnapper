# Changelog

All notable changes to this project are documented here. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); the project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

[1.0.0]: https://github.com/AES256Afro/VideoKidnapper/releases/tag/v1.0.0
