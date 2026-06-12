# Roadmap

Planned fixes, changes, and feature work for VideoKidnapper, organized by theme and
priority. Written against `main` at v1.2.0 (post PR #34). Companion to
`docs/BLUEPRINT.md`, which describes what already exists; this file describes what
should exist next.

Priority key: **P1** = next release candidates, **P2** = strong candidates after that,
**P3** = valuable but not urgent. Effort key: **S** (< 1 day), **M** (1-3 days),
**L** (a week or more of focused work).

---

## 1. Fixes and stability

### 1.1 Replace `tempfile.mktemp` with `mkstemp` in the GIF palette path — P1 / S

`core/ffmpeg/encode.py` builds palette files via `tempfile.mktemp(suffix=".png")`
(`trim_to_gif`, `frames_to_gif`). `mktemp` is deprecated and race-prone: the name is
reserved without creating the file. Two concurrent GIF exports (now reachable via the
Batch Export tab) can collide. Switch to `tempfile.mkstemp` + `os.close(fd)`, and wrap
palette cleanup in `try/finally` so a failed first pass never leaves orphan PNGs.

### 1.2 yt-dlp self-update — P1 / S

yt-dlp breaks whenever a platform changes its player; a stale copy is the most common
real-world failure of the URL tab. Add:

- A "Update downloader" button on the URL tab (and a row in the Setup dialog) that runs
  `pip install -U yt-dlp` in a worker thread and reports the old/new version.
- Detection: when a download fails with a known extractor-error signature, the error
  toast suggests updating.
- For the PyInstaller `.exe` (pip unavailable): use yt-dlp's release JSON to detect
  staleness and link the user to a new app release instead.

### 1.3 Download retry and resume — P1 / M

`core/downloader.py` makes one attempt. Add bounded retries with backoff for transient
network failures (yt-dlp distinguishes `DownloadError` causes), and pass
`continuedl=True` so a partially downloaded file resumes instead of restarting. Surface
the attempt count in the batch panel row status.

### 1.4 Disk-space and writability preflight before export — P2 / S

A long encode that dies at 99% because the output drive filled up is a terrible failure
mode. Before launching ffmpeg, check `shutil.disk_usage` against the size estimate that
`utils/size_estimator.py` already computes, and verify the output folder is writable.
Warn, do not block (estimates are estimates).

### 1.5 Stale temp-file sweep — P2 / S

Crashes can leave intermediate files behind (GIF palette PNGs, the image-overlay
intermediate MP4, screen-recording scratch files). On startup, sweep the app temp dir
for files older than N days. Pure helper + unit tests; call it from `app.py` startup.

### 1.6 Single-instance guard for settings safety — P3 / S

Two app instances share `~/.videokidnapper_settings.json`. Writes are atomic
(`utils/settings.py`), but last-writer-wins can still drop the other instance's history
entries. Either detect a second instance and warn, or merge history on write. Low
urgency; the atomic-write fix already removed the corruption risk.

### 1.7 ffmpeg progress parse hardening — P3 / S

Progress parsing in `core/ffmpeg/_internals.py` assumes well-formed `-progress` output.
Locale-odd builds and `N/A` values should degrade to an indeterminate progress bar, not
a stuck one. Add unit tests feeding malformed progress lines.

---

## 2. More robust text video editing

The text pipeline today: font, size, color, 7 anchors + free drag with snap, background
box, per-layer timing, symmetric fade. Everything below builds on
`_build_drawtext_filter` in `core/ffmpeg/filters.py` and the live PIL preview in
`ui/video_player.py`. The standing rule applies to every item: **preview and export must
render identically**, so each feature lands in both code paths in the same PR.

### 2.1 Text outline and shadow — P1 / M

The single most-requested capability for social-style captions. drawtext supports both
natively:

- Outline: `borderw=N:bordercolor=...` (the classic white-text-black-outline meme look).
- Shadow: `shadowx=N:shadowy=N:shadowcolor=...`.

Plan: add `borderw`, `bordercolor`, `shadowx`, `shadowy`, `shadowcolor` to the layer
dict (defaults preserve current output), expose Outline and Shadow controls in
`TextLayerRow`, replicate in the PIL preview via `ImageDraw.text(stroke_width=,
stroke_fill=)` for outline and a double-draw offset pass for shadow. Update the style
presets: Subtitle gains a 2px black outline by default (industry norm). Tests cover the
filter string and neutral-value omission.

### 2.2 Bold / italic via font-variant resolution — P1 / M

`_find_font_path` resolves a family name to one file. Extend it to prefer the
`Bold` / `Italic` / `Bold Italic` variant file when the layer asks for it (match on
filename conventions: `arialbd.ttf`, `ariali.ttf`, etc., with graceful fallback to the
regular face). Add B / I toggle chips to the layer row. PIL preview uses the same
resolved path, so preview parity is automatic.

### 2.3 Multiline text with alignment — P1 / M

Captions wrap. drawtext honors `\n` in the text value (needs care in
`escape_drawtext_value`) and `text_align` for per-line alignment on newer ffmpeg.
Plan: turn the single-line entry into a small `CTkTextbox`, escape newlines correctly,
add a Left / Center / Right alignment control, and mirror line breaking + alignment in
the PIL preview (the preview already measures text, so this is mostly layout math).
Probe ffmpeg version for `text_align` support and fall back to left-align with a hint.

### 2.4 Per-layer opacity — P2 / S

A fade expression already exists (`_fade_alpha_expr`); a static `alpha=0.x` is the
trivial cousin. Add an opacity slider (0-100%) to the layer row, multiply it into the
fade expression when both are set. Preview: PIL text drawn onto an RGBA scratch layer
composited at the layer alpha.

### 2.5 Text animation presets — P2 / L

Beyond fade: a small set of arrival/exit animations compiled to drawtext expressions.

- **Slide in** (from left/right/bottom): time-dependent `x=` / `y=` expressions.
- **Typewriter**: progressive reveal. drawtext cannot substring by time, so implement as
  N stacked drawtext filters with staggered `enable=between(t,...)` windows (cap
  caption length, or generate per-word rather than per-character).
- **Karaoke word highlight**: pairs with Whisper word timestamps (see 2.8).

Keep the registry data-driven (like `platform_presets.py`) so presets are testable as
pure expression builders. Preview can approximate animations at scrub time by evaluating
the same expressions in Python.

### 2.6 Rich color: full alpha + gradient presets — P3 / M

The color picker produces solid colors. drawtext accepts `fontcolor=white@0.8` style
alpha suffixes (cheap, fold into 2.4). True gradient text needs a different technique
(text as alpha mask over a gradient source); prototype before promising.

### 2.7 Text style copy/paste between layers — P3 / S

"Make this layer look like that one." Copy Style / Paste Style buttons that move
everything except text + timing. Pure dict surgery on the layer data, easy win for
multi-caption workflows.

### 2.8 Whisper word-level timestamps — P2 / M

`faster-whisper` exposes per-word timing. Upgrade `core/whisper_captions.py` to request
word timestamps and offer two import modes: current per-segment layers, or per-word
layers (which is what the karaoke preset in 2.5 consumes). Conversion is pure and
unit-testable.

### 2.9 SRT round-trip export — P2 / S

`utils/srt_parser.py` reads SRT into layers; add the inverse, layers to SRT, so users
can edit captions in the app and export the subtitle file alongside the video. This is
also the foundation for soft-subtitle muxing (`-c:s mov_text`) as a later follow-up.

---

## 3. GIF creation options

The GIF path is a fixed two-pass palettegen/paletteuse pipeline: fps and max colors from
the quality preset, dithering hardcoded to `bayer:bayer_scale=5`, loop hardcoded to
infinite. Everything below is parameterization plus a few new capabilities, mostly in
`core/ffmpeg/encode.py::trim_to_gif` and a new GIF section in `ui/export_options.py`.
All GIF options should persist via a settings schema bump (additive, v5).

### 3.1 Dithering control — P1 / S

Dithering dominates GIF look and size. Expose a dropdown:

- `bayer` scale 1-5 (current default at 5): retro/patterned, smaller files.
- `floyd_steinberg`: smoother gradients, bigger files, the GIPHY look.
- `sierra2_4a`: middle ground.
- `none`: flat-color sources (screen recordings, UI captures) compress dramatically
  better without dithering.

One token in the `paletteuse=` filter string. Pure builder + tests.

### 3.2 Palette stats mode — P1 / S

`palettegen=stats_mode=diff` weights the palette toward moving regions, a big quality
win for clips with static backgrounds (reaction GIFs, screen recordings). Expose
Full / Motion (diff) as a toggle next to the dither control.

### 3.3 Loop control — P1 / S

`-loop` is hardcoded to `0` (forever). Expose Forever / Once / N times. Trivial flag
change; matters for Slack and for GIFs used as one-shot demos.

### 3.4 Boomerang / reverse / ping-pong — P2 / M

The signature social GIF effect. `reverse` filter for reverse; ping-pong via
`split [a][b]; [b] reverse [r]; [a][r] concat`. Memory scales with clip length since
`reverse` buffers all frames, so gate it to short ranges (warn above ~10s at preset
fps). Add Forward / Reverse / Boomerang to the GIF options group.

### 3.5 Target-file-size export — P2 / L

"Make it fit under 8 MB for Discord" is the GIF user's #1 practical problem. Iterative
approach: encode, check size, and if over budget walk down a quality ladder (reduce
width, then fps, then colors) until it fits or quality floor is hit. The size estimator
provides the starting guess so most clips converge in 1-2 attempts. Show the ladder
steps in the progress dialog ("try 2: 480px / 12fps..."). Wire the existing Discord and
Slack platform presets to set the corresponding budget automatically.

### 3.6 Per-export GIF fps and width overrides — P2 / S

Quality presets bundle fps/width/colors. Power users want "High colors but 12 fps".
Add optional fps and max-width overrides in the GIF options group that take precedence
over the preset values. Keep presets as the default path.

### 3.7 Transparent GIF support — P3 / M

For sticker-style GIFs: a chroma-key color picker (`colorkey` filter) plus
`palettegen=reserve_transparent=1`. Niche but unique; few desktop tools do this well.

### 3.8 Animated WebP and APNG as sibling formats — P3 / M

Same trim/overlay pipeline, modern formats: WebP is dramatically smaller than GIF at
equal quality and is accepted by most chat platforms. Add `WEBP` (and optionally
`APNG`) to the format dropdown; encode is a straight `-c:v libwebp` mapping with
quality from the preset CRF. Verify libwebp presence via the encoder probe and hide the
option when missing.

### 3.9 GIF-native image overlays — P3 / M

Already on the blueprint's deferred list: image overlays currently route through an
intermediate MP4 before the palette passes. Compose the overlay chain directly into the
palette `filter_complex` to remove one full encode pass. Pure speed win, no UX change.

---

## 4. New features (general)

### 4.1 Blurred-background aspect fill — P1 / S

When converting 16:9 to 9:16 (Shorts/Reels/TikTok), offer Fill (blur) alongside the
current crop: `split [m][b]; [b] scale=...:...,boxblur=20 [bg]; [bg][m] overlay=...`.
The expected modern look, one new builder in `core/ffmpeg/filters.py` slotted into the
fixed filter order, plus a Fit / Crop / Blur-fill choice in Export Options. PIL preview
approximates with a Gaussian-blurred letterbox.

### 4.2 Background music / audio overlay track — P1 / L

The biggest missing primitive for social clips. An Audio panel (sibling of Text and
Image layers): pick an audio file, volume slider, fade in/out, loop-to-length toggle,
and a "duck original audio" option. Compiles to `amix` / `volume` / `afade` filters.
Largest single feature on this roadmap; design the layer dict and filter builder first,
pure-function style, before touching UI.

### 4.3 Silence-based auto-cut — P2 / M

Run `silencedetect`, convert the silence report into queued trim ranges that skip the
gaps, and let the existing multi-range + concat + transition machinery do the rest.
Turns the app into a one-click jump-cut tool for talking-head and lecture content.
Parser for silencedetect output is pure and unit-testable.

### 4.4 More download platforms — P2 / S

yt-dlp already handles TikTok, Twitch clips, Vimeo, and Streamable. Surface them:
regex in `config.py`, format-selector branch in `core/downloader.py`, chip color/glyph
in `ui/theme.py`, share target where applicable, tests in `test_platform_detect.py`.
The blueprint documents this exact recipe.

### 4.5 Project save/load (.vidkid sessions) — P2 / M

The undo system already snapshots the full editor state (layers, crop, ranges, queue).
Serialize that same snapshot to a JSON project file with Save / Open Project menu
entries and most-recent-project reopening. Versioned schema from day one, same
additive-migration discipline as settings.

### 4.6 Region and multi-monitor screen capture — P2 / M

`core/screen_capture.py` records the primary monitor only. mss exposes per-monitor
geometry: add a monitor picker and a drag-to-select region overlay (borderless
fullscreen Tk window with a rubber-band rectangle). Also add a "capture system audio"
stretch goal note: loopback capture is platform-specific and may stay out of scope.

### 4.7 Custom user presets — P3 / S

Let users save the current Quality + Format + aspect + GIF options bundle under a name,
listed in the Platform dropdown under a "My presets" divider. Persist in settings.

### 4.8 Drag-to-reorder queued ranges — P3 / S

The multi-range queue is the compilation primitive but reordering means delete + re-add.
Add drag handles or up/down buttons per row in `ui/multi_range.py`, plus an optional
per-range label shown in the concat progress.

---

## 5. Code health

### 5.1 Split `trim_tab.py` and `video_player.py` — P2 / L

1081 and 1035 lines respectively, and items 2.x / 3.x above land mostly in these files.
Split before stacking more on top: extract canvas interaction (crop drag, text/image
drag, snap rendering) from `video_player.py`, and layer-panel coordination + export
orchestration from `trim_tab.py`. Behavior-preserving refactor PRs with no feature
changes mixed in.

### 5.2 Headless UI smoke tests — P2 / M

The `ui/` layer is effectively untested (219 tests are nearly all pure-function). Tk
runs headless on CI with a virtual display (Ubuntu: xvfb). Start with the highest-churn
seams: snapshot/apply round-trip in TrimTab, platform-preset revert-to-Custom logic,
batch queue persistence restore. Even 15-20 widget tests would materially de-risk the
roadmap above.

### 5.3 Migrate off the `ffmpeg_backend` facade — P3 / M

Blueprint-stated endgame: move call sites to `core/ffmpeg/` submodule imports, then
shrink the 96-line facade to a deprecation stub for plugin authors.

### 5.4 Expand the mypy allowlist — P3 / ongoing

`mypy.ini` is strict-by-default with per-module opt-outs. Each new pure module (filter
builders, parsers from this roadmap) ships typed; flip existing `core/` modules into
the allowlist opportunistically.

---

## 6. Distribution and trust

### 6.1 Complete the v1.2.0 release gates — P1 / S

Tag-readiness blockers from the blueprint: configure PyPI Trusted Publishing, create
the `homebrew-videokidnapper` tap repo, then `git tag v1.2.0 && git push --tags`.
Everything else on this roadmap targets v1.3.0+.

### 6.2 Code signing — P3 / blocked on budget

Unsigned `.exe` trips SmartScreen on first download. Needs an EV or OV cert
($200-400/yr) or Azure Trusted Signing (~$10/mo, lighter validation). A budget
decision, not an engineering one; revisit when download volume justifies it.

---

## Suggested sequencing

**v1.3.0 (quality + robustness pass)**
1.1 mktemp fix, 1.2 yt-dlp update, 1.3 retry/resume, 2.1 outline/shadow,
2.2 bold/italic, 2.3 multiline, 3.1 dither, 3.2 stats mode, 3.3 loop control,
4.1 blur fill, 6.1 release gates. Theme: every existing workflow gets sturdier and the
text/GIF output stops looking dated.

**v1.4.0 (creation power pass)**
4.2 audio track, 3.4 boomerang, 3.5 size targeting, 2.4 opacity, 2.8 word timestamps,
2.9 SRT export, 4.3 silence auto-cut, with 5.1 (file splits) landing first since most
of these touch the same two files.

**v1.5.0+**
2.5 text animations, 3.7 transparency, 3.8 WebP/APNG, 4.5 projects, 4.6 region capture,
and the remaining P3s as interest dictates.

---

*Update this file in the same PR that ships or re-scopes an item, the same discipline
BLUEPRINT.md asks for.*
