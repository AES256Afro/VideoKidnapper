# Project blueprint

**Audience:** someone (human or AI assistant) dropping into this repo cold and needing to get productive in one sitting. Read this first; it points at the other docs for anything deeper.

Last updated: **2026-04-18** (v1.2.0 prep complete; tag not yet pushed).

---

## The 30-second elevator

VideoKidnapper is a **dark-themed desktop video editor** for short clips — trim, caption, overlay, export as MP4 or GIF. Python + CustomTkinter + ffmpeg. Cross-platform (Windows / macOS / Linux). Single maintainer (`AES256Afro`), Apache-2.0 licensed.

Core workflows:

- **Trim Video** tab — load a local file, scrub via thumbnails + waveform, drag text layers + PNG overlays on the preview, queue multiple ranges for compilation, export with color grading / speed / aspect / transitions.
- **URL Download** tab — paste a YouTube / Instagram / Bluesky / X / Reddit / Facebook link, batch-download, feed the result into the trim workflow.
- **Auto-captions** via faster-whisper run the current trim range through Whisper → text layers.
- **Screen recording** captures your monitor directly into the trim workflow.
- **CLI mode** (`videokidnapper --url … --start 10 --end 25 --format GIF`) bypasses the GUI entirely.

The app doesn't bundle ffmpeg (GPL redistribution reasons); the in-app **⚙ Setup** dialog pulls a portable build on first launch, or users install via winget/brew/apt.

---

## Current state as of 2026-04-18

**On `main`:** 11 feature / fix / refactor PRs merged in one session (see the 2026-04-18 section of `CHANGELOG.md`). Tests: **219 passed + 1 skipped** (integration, no local ffmpeg). Ruff + mypy (per the soft-start allowlist) both clean.

**Version bump:** `__version__` is still `1.1.0` on main. The 1.2.0 bump lives on the unmerged `chore/v1.2.0-release-prep` PR alongside Homebrew / winget templates and `docs/RELEASE.md`.

**Ready to tag `v1.2.0` once:**

1. `chore/v1.2.0-release-prep` merges (brings the version bump, PyPI packaging metadata, Homebrew template, winget manifests, release playbook).
2. The maintainer configures PyPI Trusted Publishing (one-time; see `docs/RELEASE.md`).
3. An empty `AES256Afro/homebrew-videokidnapper` tap repo is created.

After those three, `git tag v1.2.0 && git push --tags` triggers:

- `.github/workflows/release.yml` → builds sdist + wheel, publishes to PyPI, attaches to GitHub Release.
- `.github/workflows/installer.yml` → builds `VideoKidnapper.exe` (portable) + `VideoKidnapper-Setup-1.2.0.exe` (Inno Setup wizard), attaches both to the GitHub Release.
- Manual: fill SHA256s into Homebrew formula + winget manifests, publish both.

---

## Architecture at a glance

```
videokidnapper/
├── __init__.py              # single source of truth for __version__
├── app.py                   # Tk root, header, tab wiring, plugin loader
├── cli.py                   # argparse → either CLI or `App().mainloop()`
├── config.py                # PRESETS (TypedDict), paths, platform regexes
├── core/
│   ├── downloader.py        # yt-dlp wrapper: download_video, probe timeout
│   ├── ffmpeg_backend.py    # ← THIN FACADE (96 lines) re-exporting from …
│   ├── ffmpeg/              # … the split subpackage
│   │   ├── __init__.py      # public-API re-exports
│   │   ├── _internals.py    # binaries, HW encoder probe, progress, failures
│   │   ├── probe.py         # ProbeError, get_video_info, extract_frame, extract_waveform
│   │   ├── filters.py       # every filter-string builder + _assemble_video_filters
│   │   ├── encode.py        # trim_to_video / trim_to_gif / frames_to_…
│   │   └── concat.py        # concat_clips + concat_clips_with_transition
│   ├── playback.py          # AudioVideoPlayer (imageio-ffmpeg + sounddevice)
│   ├── preview.py           # LRU frame cache, thumbnail extractor
│   ├── screen_capture.py    # mss-based screen record
│   └── whisper_captions.py  # faster-whisper integration
├── plugins/                 # third-party plugin infrastructure
│   ├── base.py              # Plugin base class
│   ├── discovery.py         # entry_points-based loader + version gating
│   └── __init__.py
├── ui/
│   ├── trim_tab.py          # ← the biggest tab; text/image layers, undo, transitions
│   ├── url_tab.py           # URL download UI + batch panel
│   ├── history_tab.py       # recent-exports list
│   ├── debug_tab.py         # stdout/stderr tail with level colors
│   ├── video_player.py      # preview canvas; crop + text-drag + snap + A/V playback
│   ├── text_layers.py       # drawtext overlay panel
│   ├── image_layers.py      # PNG overlay panel
│   ├── thumbnail_strip.py   # scrubbable thumb row above waveform
│   ├── waveform.py          # live-extract + selection overlay
│   ├── multi_range.py       # queue of trim ranges + concat toggle
│   ├── export_options.py    # speed / rotate / aspect / color / transitions
│   ├── export_dialog.py     # modal progress + share-to-platform panel
│   ├── setup_dialog.py      # FFmpeg + pip-packages auto-installer
│   ├── batch_queue.py       # batch URL download panel
│   ├── share_panel.py       # clipboard + platform-compose-page share
│   ├── widgets.py           # RangeSlider, TimestampEntry, PlatformChip, Toast
│   ├── theme.py             # dark/light design tokens
│   └── color_picker.py      # custom-color dialog
└── utils/
    ├── settings.py          # JSON persistence with schema migration + write lock
    ├── ffmpeg_check.py      # PATH + portable-install binary resolution
    ├── ffmpeg_escape.py     # lavfi escaping (drawtext values, paths)
    ├── file_naming.py       # timestamped export paths with collision handling
    ├── github_update.py     # async update check on startup
    ├── prereq_check.py      # Setup dialog's "what's missing" probe
    ├── share.py             # platform share-URL builders + clipboard
    ├── size_estimator.py    # pre-export file-size estimates
    ├── srt_parser.py        # SRT → text-layer dicts
    ├── time_format.py       # HH:MM:SS.mmm ↔ seconds
    ├── dnd.py               # tkinterdnd2 file-drop parser
    ├── snap.py              # Figma-style snap math (pure, fully typed)
    └── undo.py              # bounded undo/redo stack (pure, fully typed)

tests/           # 219 tests; mostly pure-function; one integration test
packaging/
├── videokidnapper.spec          # PyInstaller
├── inno-setup/videokidnapper.iss # Windows installer wizard
├── homebrew/videokidnapper.rb    # Formula template for personal tap
└── winget/manifests/1.2.0/*.yaml # winget submission set
docs/
├── PLUGINS.md                # third-party plugin API + packaging guide
├── RELEASE.md                # cut-a-release playbook
└── BLUEPRINT.md              # THIS FILE
examples/
└── plugins/videokidnapper_hello/  # reference "Hello" plugin
```

## Key layering rules

1. **Anything in `core/` does not import from `ui/`.** This is enforced by convention; tests run without Tk for most of the suite.
2. **Filter-graph construction is pure.** `core/ffmpeg/filters.py` is a bunch of pure functions returning strings. Makes the test pyramid fat: filter math is covered by unit tests, encode wiring by one integration test that actually runs ffmpeg.
3. **Settings live in `~/.videokidnapper_settings.json`.** Schema versioned (`_version` key), migrations in `utils/settings.py`. **Current schema: v3.** When adding settings, bump to v4 with an additive-only migration.
4. **Optional deps degrade gracefully.** Every heavy dep (tkinterdnd2, imageio-ffmpeg, sounddevice, numpy, faster-whisper) is importable-checked at runtime. Missing → feature silently disables or shows an install hint. Core install stays minimal.
5. **Backwards-compat facade.** `core/ffmpeg_backend.py` re-exports the entire split subpackage so external callers don't have to update imports. Future work can migrate call sites to the submodule paths, then shrink the facade.

---

## Design decisions worth remembering

### Why snapshots instead of command-pattern undo

Editor state is small (text layers + image layers + crop + range + queue ≈ a few hundred bytes). Full-state snapshots on every "settled" edit (350ms debounce) are trivially cheap and make restore bulletproof. Command-pattern undo demands a symmetric `apply` / `unapply` pair for every mutation path — more code, more chances to diverge from the forward flow.

**Cap is 50 snapshots**, hard-coded in `TrimTab.__init__`. Raise if memory is a concern later; unlikely to matter.

### Why audio is the master clock for A/V playback

Standard video-player wisdom: audio drift is perceptible at ~30ms; video drift isn't perceptible until ~100ms. Audio hardware also has stable latency, so `samples_played / sample_rate` is a rock-solid clock. Silent clips fall back to `time.monotonic()` so video never stalls waiting for audio that doesn't exist.

See `core/playback.py::AudioClock`.

### Why overlays render AFTER text at export time

Export filter graph:
```
[0:v] <geometric_ops>, drawtext, drawtext, …, scale [vbase];
[vbase][1:v] overlay=…,
[v1][2:v] overlay=… [vout]
```

Image overlays layer on top of text. Live preview mirrors this with `_apply_text_overlay` → `_apply_image_overlay`. **If you change one order, change both** — preview/export divergence is the #1 class of bug here.

### Why filter order is fixed

`_assemble_video_filters` (in `core/ffmpeg/filters.py`) emits filters in this order, *always*:

```
(aspect-crop) → crop → rotate → color-eq → speed → drawtext → scale
```

Drawtext MUST come before scale so fontsize + x/y are interpreted in source-frame pixels — that's the space the preview overlay uses. Swap the order and custom drag positions land at wrong pixels on the exported preset-scaled frame. This was a real bug (fixed in v1.1.0, documented in CHANGELOG).

### Why a facade for `ffmpeg_backend.py`

The file grew from ~400 to ~1200 lines across v1.1 and v1.2. Refactor split it into six focused files under `core/ffmpeg/`, but external callers (`trim_tab.py`, `url_tab.py`, tests, CLI) had hundreds of import statements referencing `ffmpeg_backend.<thing>`. A 96-line facade keeps every existing import working. Future work can migrate call sites to submodule paths and eventually retire the facade.

### Why Apache-2.0 and not GPL

v1.0 was GPLv3. Relicensed to Apache-2.0 in v1.1 for two reasons:

1. Permissive licensing matches "broad adoption / corporate-friendly / possible future paid tier" goals better than copyleft.
2. The plugin system (`videokidnapper.plugins` entry-point group) means third-party plugins can pick any license — MIT, GPL, proprietary — because the entry-point mechanism is packaging-level, not source-level. Apache-2.0 does not infect via `pip install`. This was intentional architecture.

Tags up to `v1.0.0` remain available under GPLv3. Apache-2.0 applies to v1.1.0+.

### Why settings use atomic writes

Batch exports used to lose history entries because two threads did unsynchronized read-modify-write on `~/.videokidnapper_settings.json`. Fix: module-level `_WRITE_LOCK` guards read-modify-write, and writes go through `tempfile.mkstemp + os.replace` for filesystem atomicity. `os.replace` is atomic on both POSIX and Windows.

See `utils/settings.py::_write` and the locking around `set` / `update` / `add_history_entry`.

### Why ffprobe errors became `ProbeError`

`json.loads(result.stdout)` used to land uncaught `JSONDecodeError` into the Tk event loop whenever a file was corrupt / half-downloaded / ffprobe was killed. Now every ffprobe failure mode (missing binary, timeout, non-zero exit, bad output) raises `ProbeError` with a human-readable reason. Callers (`TrimTab._load_path`, CLI) already caught generic `Exception` so this is wire-compatible.

### Why yt-dlp probe runs on a worker thread

yt-dlp has no native timeout knob for `extract_info`. A stalled CDN (dead server, rate-limited, captcha page) hangs the UI indefinitely. Fix in `core/downloader.py::get_video_info_from_url`: run the extract on a daemon thread with `thread.join(timeout)`. If the thread's still alive after the timeout we return an error dict; the thread is reaped on process exit.

---

## Distribution pipeline (four channels, gated on `vX.Y.Z`)

| Channel | Trigger | Artifact | Who maintains |
|---|---|---|---|
| **PyPI** | `.github/workflows/release.yml` on tag push | sdist + wheel | automated (OIDC) |
| **GitHub Release** | release.yml + installer.yml on tag push | sdist, wheel, `VideoKidnapper.exe`, `VideoKidnapper-Setup-X.Y.Z.exe` | automated |
| **Homebrew tap** | manual, post-release | `AES256Afro/homebrew-videokidnapper` formula | manual |
| **Winget** | manual, PR to `microsoft/winget-pkgs` | manifest files at `manifests/a/AES256Afro/VideoKidnapper/X.Y.Z/` | manual (bot-reviewed) |

Full playbook in `docs/RELEASE.md`. Short version: bump `__version__`, datestamp the `[Unreleased]` CHANGELOG block, merge, tag `vX.Y.Z`, wait for workflows, then fill Homebrew SHA256 (from PyPI sdist) + winget SHA256 (from release `.exe`) and publish both.

### One-time setup required before the first automated release

**PyPI Trusted Publishing** — needs a pending publisher configured on pypi.org:
- Owner: `AES256Afro`
- Repo: `VideoKidnapper`
- Workflow: `release.yml`
- Environment: `pypi`

See `docs/RELEASE.md` for details. Without this, `release.yml` fails at the publish step.

---

## Testing

- **Unit tests** — 200+ pure-function tests covering URL detection, filter construction, snap math, undo math, settings migration, SRT parsing, size estimation, plugin discovery, Whisper entry conversion, xfade filter builder, image-overlay chain builder, color filter builder, transition labels.
- **Integration test** — `tests/test_integration_ffmpeg.py` runs a real ffmpeg with a synthetic `lavfi` source through the full `trim_to_video` path. Skips automatically when ffmpeg isn't on PATH; CI installs ffmpeg (apt on Ubuntu, choco on Windows) so it always runs there.
- **License-header test** — `tests/test_license_headers.py` enforces the SPDX Apache-2.0 marker on every `.py` file. CI tripwire; a PR missing headers fails here.

Run locally:
```bash
python -m pytest tests/ -q
python -m ruff check videokidnapper/ main.py scripts/ tests/
python -m mypy --config-file mypy.ini videokidnapper
```

CI (on Ubuntu + Windows × Python 3.11 / 3.12) runs all three on every PR and push to main.

---

## Open PRs (as of 2026-04-18)

| # | Branch | Purpose | Conflict risk |
|---|---|---|---|
| [#21](https://github.com/AES256Afro/VideoKidnapper/pull/21) | `chore/v1.2.0-release-prep` | Version bump + PyPI pyproject + Homebrew / winget templates + RELEASE.md | Low — mostly new files + `__init__.py` + `pyproject.toml` |
| [#22](https://github.com/AES256Afro/VideoKidnapper/pull/22) | `refactor/ffmpeg-backend-split` | Split 1200-line `ffmpeg_backend.py` into 6 focused submodules under `core/ffmpeg/`; keep facade | Conflicts with #23 and #25 on imports — merge this first or last, not middle |
| [#23](https://github.com/AES256Afro/VideoKidnapper/pull/23) | `feat/image-overlay-finish` | Live preview + GIF export support for image overlays | Low — mostly additive |
| [#24](https://github.com/AES256Afro/VideoKidnapper/pull/24) | `feat/inno-setup-installer` | Inno Setup Windows installer + updated `installer.yml` | Low — new files + one workflow edit |
| [#25](https://github.com/AES256Afro/VideoKidnapper/pull/25) | `chore/mypy-in-ci` | mypy in CI with per-module allowlist | Low — new `mypy.ini`, small type-hint additions |
| [#26](https://github.com/AES256Afro/VideoKidnapper/pull/26) | `docs/blueprint` | This document | None |

Plus two Dependabot PRs (#2, #3 — action version bumps) that existed before this session.

### Suggested merge order

1. **#25 mypy** — no conflicts, establishes a new CI signal.
2. **#24 Inno Setup** — no code changes, only CI + new packaging files.
3. **#23 image overlay finish** — extends existing files additively.
4. **#22 ffmpeg split** — biggest refactor; do it before the release-prep PR bumps to 1.2.0 so the split is in the release.
5. **#21 release prep** — last, so 1.2.0 ships with everything above.
6. **#26 blueprint** — independent, merge whenever.

Only real conflict: **#22 vs. #23**. Both touch `ffmpeg_backend.py` — #23 adds image-overlay support to `trim_to_gif` via the MP4 intermediate shortcut. If #22 (the split) lands first, #23 will need to be rebased to target `core/ffmpeg/encode.py` instead. The rebase is mechanical (move the edit target), but someone has to do it.

---

## Outstanding roadmap items

Everything that was on the roadmap is either shipped or has an open PR. Explicitly deferred items:

- **Code signing for the `.exe`** — needs an EV cert ($200–400/yr) + maintainer setup. Unsigned `.exe`s trigger SmartScreen warnings on first run; acceptable for now.
- **Start-Menu-integrated auto-updater** — the app already checks GitHub for new releases on launch (`utils/github_update.py`). Adding a separate updater service inside the installer wouldn't pay for itself.
- **MSI installer (WiX) as alternative to Inno Setup** — future work if org IT requires MSI-specific deploy. Inno Setup covers the consumer case.
- **Splitting `trim_tab.py`** — it's ~900 lines now. Not urgent; the file is well-organized internally. Future refactor candidate.
- **Type hints across `ui/`** — Tkinter + customtkinter have no usable stubs. Pass at this only after the stubs ecosystem improves.
- **GIF-native image-overlay filter_complex** — current implementation shortcuts via an intermediate MP4. Works, slower than necessary. Future optimization.

---

## Development workflow

### Branch naming

- `feat/<slug>` — new features (user-visible)
- `fix/<slug>` — bug fixes
- `refactor/<slug>` — non-behavior-changing code reorgs
- `chore/<slug>` — infra, docs, release prep
- `docs/<slug>` — documentation-only changes

### PR format

Follow `.github/PULL_REQUEST_TEMPLATE.md` — Summary / Why / Test plan / License / Notes. All four sections are expected; reviewers read the Notes section first for design decisions.

### CI gates

Every PR must pass:
- `Tests on ubuntu-latest / Python 3.11`
- `Tests on ubuntu-latest / Python 3.12`
- `Tests on windows-latest / Python 3.11`
- `Tests on windows-latest / Python 3.12`
- `Ruff`
- `mypy`

Branch protection on `main` enforces these — you cannot merge a PR with failing checks.

### Commit message style

Existing pattern: `<imperative subject>: <what changed / why>\n\n<body paragraphs>\n\nCo-Authored-By: …`. Look at recent main commits for the house style.

---

## Known gotchas

### Windows line-endings

Git warns about LF → CRLF conversion on most commits. This is harmless — the repo uses `.gitattributes`-less defaults and Git handles it automatically. Don't chase these warnings.

### `ffmpeg_backend.py` vs. `core/ffmpeg/`

After PR #22 merges, the facade file stays around for backwards compat. You can import from either location and it works. For NEW code, prefer the submodule path (`from videokidnapper.core.ffmpeg.filters import _build_eq_filter`) so the migration-away-from-facade path is easier later.

### Settings file versioning

The `_version` key in `~/.videokidnapper_settings.json` must only go UP, and migrations must be additive. **Never rename or delete a setting key** — future versions reading the file would not find their expected keys and fall back to defaults, losing user state silently. If a rename is unavoidable, add a new schema version that migrates the old key's value forward and leaves the old key in place (harmless orphan).

### Optional-dep checks

The pattern is always **check at the entry point, not at import**:

```python
# GOOD:
def _auto_caption(self):
    from videokidnapper.core import whisper_captions
    if not whisper_captions.is_available():
        self._notify("faster-whisper not installed…", "error")
        return
    # ... proceed

# BAD:
from videokidnapper.core import whisper_captions  # explodes at module load
```

The module-level imports in core files that wrap optional deps use lazy imports inside function bodies for the same reason. Don't hoist them.

### Tk threading

Tkinter is not thread-safe. Every worker thread that wants to touch the UI must marshal back via `widget.after(0, callback, *args)`. Search the codebase for `self.after(0,` to see the pattern. Workers that miss this cause random crashes under load.

### CustomTkinter quirks

- `CTkTabview.add("text")` uses the literal "text" string as the tab ID. Getting a tab back needs the EXACT same string including surrounding whitespace. Hence the padded tab names (`"  ✂  Trim Video  "`).
- `CTkOptionMenu.configure(command=...)` fires on every selection including programmatic `.set()`. Use a `_restoring` guard flag (see `TrimTab._apply_snapshot`) when updating values programmatically.
- `CTkFrame.pack_propagate(False)` is required to lock a fixed height — otherwise children resize the parent. This is how `VideoPlayer` maintains its 380px preview area inside the scrollable tab.

---

## Starting points for common work

### "I want to add a new filter / effect"

1. New builder function in `core/ffmpeg/filters.py` — pure, returns a string or `None` (no-op).
2. Slot it into `_assemble_video_filters` in the right order (read the docstring there).
3. Add a row to `ui/export_options.py` with a Tk var, wire it to `_save` and `get_options`.
4. Add the setting key + default to `utils/settings.py::_DEFAULTS` and bump the schema version with an additive migration.
5. Write tests in `tests/test_<filter>.py` covering the pure function (neutral detection, value clamping, chain ordering).

### "I want to add a new tab"

Two paths:

- **Core tab** (ships in the app): add to `ui/<name>_tab.py`, register in `App._build_tabs` in `app.py`, wire keyboard shortcuts if needed.
- **Plugin tab**: subclass `videokidnapper.plugins.Plugin`, implement `on_app_ready(app)` calling `app.register_tab(name, factory)`, package as a pip-installable with an entry point in `[project.entry-points."videokidnapper.plugins"]`. See `docs/PLUGINS.md` for the full recipe.

### "I want to support a new video platform in URL Download"

1. Add platform regex to `SUPPORTED_PLATFORMS` in `config.py`.
2. Add format-selector branch to `core/downloader.py::_build_ydl_opts` (yt-dlp-format-selector docs: https://github.com/yt-dlp/yt-dlp#format-selection).
3. Add brand color + glyph to `theme.PLATFORM_COLORS` + `PLATFORM_GLYPHS` in `ui/theme.py`.
4. Add share-compose URL in `utils/share.py` if the platform accepts prefilled captions.
5. Tests: extend `tests/test_platform_detect.py` with URL patterns and `tests/test_share.py` if you added a share target.

### "I want to ship a new release"

Read `docs/RELEASE.md` end-to-end. Short version:

```bash
# 1. Bump videokidnapper/__init__.py __version__
# 2. Datestamp [Unreleased] → [X.Y.Z] in CHANGELOG.md
# 3. Merge those via PR
# 4. Tag + push
git checkout main && git pull
git tag vX.Y.Z
git push --tags
# 5. Wait for release.yml + installer.yml to finish
# 6. Update Homebrew tap with PyPI sdist SHA256
# 7. Submit winget PR with release .exe SHA256
```

### "I want to understand how feature X actually works"

Grep first. File doc-strings are written to stand alone — most modules explain themselves in the first 20 lines. The CHANGELOG's 1.2.0 section also narrates each feature with the "why" alongside the "what."

---

## Where this doc falls short

- **No screenshots.** The repo's `README.md` has the canonical screenshot set.
- **No AI-conversation-specific context.** If you're Claude picking this up in a new session, ask the user to paste the current `git log --oneline -25` so you can see which PRs have merged since this was written.
- **No "things I'd do differently" section.** Those retrospectives would be useful but premature — the codebase hasn't been in production long enough to have the benefit of hindsight.

**When this doc goes stale:** any time a major feature lands, a PR count goes out of date, or the release playbook changes. Update it in the same PR that makes the change — don't let it drift.
