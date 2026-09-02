# Milestones & Forward Plan

A long-range milestone plan for VideoKidnapper, with a security sweep, a
performance sweep, and concrete improvement suggestions. Written against
`main` at v1.8.1 (2026-08-05). Companion to `docs/ROADMAP.md` (thematic,
per-item detail) — this file is the *sequenced* plan: what ships in which
release, in what order, with exit criteria.

Priority key: **P1** next release, **P2** after that, **P3** valuable but not
urgent. Effort key: **S** (< 1 day), **M** (1–3 days), **L** (a week+).

---

## 0. Where the project stands (v1.8.1)

Facts on the ground, verified against the tree on 2026-08-28:

- ~14,300 LOC of Python across `videokidnapper/` (core, ui, utils, plugins),
  Tk/CustomTkinter desktop app, runs Python 3.9–3.14 (`pyproject.toml`).
- 500+ tests across 44 test files; nearly all pure-function. The `ui/` layer
  is effectively untested.
- Distribution surface is unusually wide for a project this size: Microsoft
  Store (MSIX), winget, Inno Setup installer, portable `.exe`, PyPI, APT
  repo, AppImage, `.deb`, macOS DMGs (arm64 + x86_64, Developer ID signed,
  **not yet notarized**), 7 CI workflows.
- v1.8.0 was a near-miss release (broken macOS bundle, broken wheel, Intel
  FFmpeg in the arm64 DMG, filter-injection CVE-class bug) all fixed in
  v1.8.1 — the recovery discipline was good, but each was a *process* gap,
  not a code gap. Several milestones below exist to close those process gaps.
- `docs/ROADMAP.md` is stale in its sequencing section: it still proposes
  "v1.3.0 / v1.4.0 / v1.5.0" while the project is at v1.8.1, and many items
  it lists as open (outline/shadow, bold/italic, multiline, dither control,
  blur fill, project files, retry/resume) have since shipped. **First
  action: reconcile the roadmap against the changelog (Milestone M0).**

---

## 1. Security sweep

Findings from a targeted pass over the tree (subprocess use, temp files,
network fetches, filter-graph construction, plugin loading, update paths).
Ordered by severity. None of these is a confirmed exploit; they are the
audit queue, in the order it should be worked.

### S1 — Filter-graph injection: audit the *remaining* drawtext fields — P1 / M

v1.8.1 fixed injection through `fontcolor` / `bordercolor` / `shadowcolor` /
`boxcolor` in `.vidkid` project files (see CHANGELOG 1.8.1 Security). The
same trust boundary still has unaudited fields: free **text** content,
**fontfile paths**, **x/y motion expressions**, and **image overlay paths**
all flow from a project file into the ffmpeg filter graph or the process
environment. A shared `.vidkid` file is an attack surface the app actively
encourages (project portability is a feature).

- [ ] Enumerate every field loaded from a project file and classify:
      validated / escaped / raw.
- [ ] Extend the v1.8.1 allowlist approach to every field that reaches a
      filter string; unit-test with hostile payloads (`'`, `:`, `,`, `[`,
      `movie=`, `file://`, absolute paths).
- [ ] Decide the policy for paths inside project files (media references
      are legitimate; anything pointing at `~/.ssh` is not).

### S2 — `tempfile.mktemp` still in two call sites — P1 / S

ROADMAP 1.1 fixed the GIF palette path in `core/ffmpeg/encode.py`, but the
pattern survives in `core/whisper_captions.py:63` (`.wav` scratch file) and
`core/ffmpeg/concat.py:244` (concat list `.txt`). Same race/collision risk,
same fix: `mkstemp` + `os.close(fd)` + `try/finally` cleanup. Sweep the
whole tree so it cannot come back (a ruff rule or a one-line test that
greps the source).

### S3 — Admin-terminal command construction — P1 / S

`utils/prereq_check.py:473-488` builds elevated-shell commands: an
`osascript -e` AppleScript string on macOS and `bash -c '{joined}'` on
Linux. Today the interpolated pieces are fixed strings, but the quoting is
hand-rolled and exactly the kind of code that breaks when someone later
adds a user-influenced value (e.g. a custom package name). Add a comment
documenting the invariant, quote with `shlex.quote` everywhere, and add a
regression test asserting the emitted command bytes.

### S4 — Plugin system executes any installed entry point — P2 / M

`plugins/discovery.py:98,110` loads and instantiates *any* distribution
that declares the `videokidnapper.plugins` entry point — by design, but it
means any pip package in the environment runs code inside the app with no
user consent moment. Mitigations in increasing order of weight:

1. Document the trust model in `docs/PLUGINS.md` (cheap, do first).
2. First-run consent dialog listing discovered plugins, persisted in
   settings, with a per-plugin disable toggle.
3. Optional allowlist of plugin distribution names in settings.

### S5 — Update/self-install network paths: integrity is per-channel, make it uniform — P2 / M

- FFmpeg download verifies a SHA-256 — but the digest comes from the *same
  origin* as the binary (`_FFMPEG_WIN_URL + ".sha256"`,
  `utils/prereq_check.py:28,107`). That is integrity against corruption,
  not authenticity against a compromised mirror. Pin the expected digest in
  the release (or a signed manifest) so the check is against a value the
  attacker would also have to replace.
- yt-dlp / GitHub update checks (`utils/ytdlp_update.py:61`,
  `utils/github_update.py:185`) are plain `urllib` over HTTPS — fine for
  *detection*, but make sure no code path ever *executes* a payload fetched
  this way without platform verification (Store/winget/APT already provide
  theirs; portable installs open the release page rather than
  self-replacing — keep it that way).
- [ ] Write one short "update trust model" table into `SECURITY.md`: per
      install channel, who signs what.

### S6 — "Open / Reveal" actions trust persisted paths — P2 / S

History and batch tabs hand stored paths to `explorer /select`, `open`,
`xdg-open` (`ui/history_tab.py:150-158`, `ui/batch_export_tab.py:465-477`,
`ui/export_dialog.py:152-154`, `ui/trim_tab.py:758-760`). The paths come
from the app's own settings file, so exposure is low — but the settings
file is user-writable JSON, and a confused-deputy trick via a tampered
settings file is not nothing. Validate: path exists, is absolute, and
resolves inside the configured output folder (or is the loaded video)
before shelling out.

### S7 — Settings file hygiene — P3 / S

`~/.videokidnapper_settings.json` carries export history and paths. Set
mode `0o600` on POSIX at write time (atomic write already exists in
`utils/settings.py`), and confirm nothing secret-adjacent (cookie file
paths, browser profile names) is ever logged to the Debug tab.

### S8 — Supply-chain hardening for CI — P2 / M

Dependabot is configured (`.github/dependabot.yml`). Add:

- `pip-audit` (or `uv pip audit`) as a non-blocking CI job, promoted to
  blocking once clean.
- Pin CI tool versions (`ruff==…`) — `pyproject.toml` comments document the
  2026-08-01 incident where a floating ruff install broke CI with 300+
  findings and no code change. Same exposure exists for every other
  bare-installed CI tool.
- The v1.8.0 wheel bug (hand-maintained package list silently dropping
  subpackages) was caught only after release; the packaging test added in
  1.8.1 is the model — extend that "test the artifact, not the intent"
  pattern to every packaged output (see M4).
- Windows binaries trip SmartScreen (unsigned); macOS is signed but not
  notarized. Both are budget milestones (M8), tracked here so the security
  story has one home.

### S9 — Out-of-scope-but-document — P3 / S

`SECURITY.md` already scopes cookie flows and dependency CVEs. Add one
line: URLs pasted into the app are passed to yt-dlp, which fetches
arbitrary network content — that is the feature, and extractor bugs are
upstream. Keeps future reports routed correctly.

---

## 2. Performance sweep

The app is I/O-bound on ffmpeg for exports; the performance work that
matters is UI responsiveness, redundant encode passes, and startup cost.

### P1 — Split the two monoliths before they grow further — P1 / L

`ui/trim_tab.py` is now **1,522 lines** and `ui/video_player.py` **1,114**
(ROADMAP 5.1 recorded them at 1,081/1,035 — they are still growing, and
every roadmap feature lands in them). This is a performance issue in the
engineering-velocity sense: merge risk, untestable seams, slow iteration.
Behavior-preserving extraction, no features mixed in:

- `video_player.py` → canvas interaction (crop/text/image drag, snap
  rendering) vs. playback state machine vs. PIL overlay rendering.
- `trim_tab.py` → layer-panel coordination vs. export orchestration vs.
  download-bar wiring.

### P2 — Remove the extra encode pass for GIFs with image overlays — P3 / M

Image overlays on the GIF path route through an intermediate MP4 before the
palette passes (ROADMAP 3.9): one full extra encode per export. Compose the
overlay chain directly into the palette `filter_complex`. Pure speed win,
no UX change.

**Measured 2026-08-29 before committing to this** — a 10 s 1080p source
exported to GIF, median of five runs:

| | |
|---|---|
| no overlay | 0.53 s |
| one overlay | 0.84 s |
| cost of the extra pass | **+0.31 s (+58%)** |

Real, but an order of magnitude smaller than the "~1–2× the GIF encode
time" this was filed on. Threading overlays through both palette passes
while keeping stream indices straight is the fiddly work `encode.py`
already documents avoiding, and 0.31 s is a poor return for that risk.
Demoted to P3: worth doing if the palette code is being opened anyway,
not worth opening it for.

### P3 — Preview/decode pipeline audit — P2 / M

- Confirm the playback decode threads (`core/playback.py:188-194`) apply
  backpressure — decode must not run ahead of the playhead and pile frames
  in memory on long files.
- Preview renders PIL frames on the Tk main loop; verify the preview cache
  (see `tests/test_preview_cache.py`) is keyed tightly enough that scrubbing
  back and forth over the same region never re-decodes.
- Thumbnail strip + waveform extraction spawn ffmpeg per video load; cache
  results on disk keyed by (path, mtime, size) so re-opening yesterday's
  project is instant.

### P4 — Startup cost: keep heavy imports lazy — P2 / S

The module-level lazy caches in `core/ffmpeg/_internals.py` (binary
resolution, encoder probing) are the right pattern — extend it: OpenCV
(`[track]`), faster-whisper, and tkinterdnd2 should never be imported until
their feature is invoked. Measure cold-start time before/after; target no
regression >50 ms on a mid-range machine.

### P5 — Batch export parallelism — P3 / M

Batch exports encode sequentially. Independent clips could encode in
parallel (a small worker pool), with two guards: hardware encoders
serialize on some platforms (probe before parallelizing), and memory
pressure scales with concurrent encodes. Default to 2 workers, cap at
`min(4, cores//2)`.

### P6 — Memory gates for frame-buffering filters — P2 / S

`reverse` (boomerang, ROADMAP 3.4) buffers every frame; so does any future
`tblend`/slow-mo work. Gate by clip length × preset fps with a clear
warning, per the existing roadmap note.

### P7 — Progress parse robustness — P3 / S

ROADMAP 1.7 (still open): malformed `-progress` output must degrade to an
indeterminate bar, not a stuck one. Also a perceived-performance bug — a
"stuck at 0%" encode reads as a hang.

---

## 3. Improvement suggestions (process & product)

Things that are neither bugs nor perf, in rough value order:

1. **Reconcile `docs/ROADMAP.md` with reality.** Its sequencing section
   targets v1.3.0–v1.5.0 from a v1.8.1 present, and lists shipped features
   as open. Adopt the same discipline BLUEPRINT asks for: update in the PR
   that ships an item. (M0 below.)
2. **Adopt a "release-gate checklist" culture.** All four v1.8.0 regressions
   (broken DMG, broken wheel, wrong-arch FFmpeg, injection bug) were classes
   of failure a checklist + artifact test catches. `docs/RELEASE.md` exists —
   add the v1.8.1 lessons to it explicitly (M4).
3. **UI smoke tests on xvfb.** 500+ tests and the entire `ui/` layer is
   untested (ROADMAP 5.2). 15–20 tests on the highest-churn seams would have
   caught whole categories of past regressions. (M5.)
4. **Version the plugin API.** `docs/PLUGINS.md` + min/max app version fields
   exist; add a stated stability policy ("filter-builder inputs are stable
   from vX; UI hooks are not") so third-party authors know what they can
   rely on.
5. **One metrics habit.** Add a tiny "export stats" line to the Debug tab
   (encode seconds, input/output MB, fps achieved). Zero telemetry, local
   only — but it gives users quotable numbers when reporting perf issues,
   and gives you a regression yardstick for the P-sweep above.
6. **Keep the changelog's voice.** The 1.7.x–1.8.x entries explain *why* in
   plain language; it is genuinely good technical writing and a differentiator
   for the Store listing. Whatever else changes, protect that.
7. **Small UX wins queue** (all S, all independent): per-range labels in
   concat progress; drag-to-reorder queued ranges (ROADMAP 4.8); style
   copy/paste between text layers (ROADMAP 2.7); custom user presets
   (ROADMAP 4.7); GIF fps/width overrides (ROADMAP 3.6).

---

## 4. The milestone list

Long-range sequence. Each milestone: theme, contents (roadmap cross-refs
where they exist), and exit criteria. Versions are labels, not promises —
scope moves, criteria don't.

### M0 — Housekeeping & roadmap reconciliation (no release, this week)

- Rewrite ROADMAP's sequencing section to post-v1.8 reality; mark shipped
  items shipped.
- Fold S1–S3 into the issue tracker as labeled security-hardening items.
- Adopt this file as the sequenced plan; ROADMAP stays the thematic detail.
- **Exit:** roadmap and changelog agree; every S-finding has an owner and a
  target milestone.

### M1 — v1.8.2: Security & robustness patch — P1 / S–M

- S1 remaining-field filter injection audit + tests.
- S2 `mktemp` eradication (whisper_captions, concat) + anti-regression test.
- S3 shlex-quoted admin terminal + regression test.
- S6 open/reveal path validation.
- ROADMAP 1.4 disk-space/writability preflight (it was next-up when
  interrupted).
- **Exit:** hostile-payload test suite for project files passes; zero
  `mktemp` in tree; release notes call out hardening.

### M2 — v1.9.0: The "finish the robustness list" release — P1 / M

- ROADMAP 1.5 stale temp-file sweep; 1.6 single-instance guard decision;
  1.7 progress-parse hardening (P7 here).
- ROADMAP 3.9 GIF-overlay single-pass encode (perf P2).
- Small UX queue: 4.8 range reorder, 2.7 style copy/paste, 3.6 GIF
  fps/width overrides.
- **Exit:** every open ROADMAP §1 item closed; GIF-with-overlay export time
  measurably reduced on the reference clip; no new UI without tests.

### M3 — v1.10.0: Audio — P1–P2 / L

- ROADMAP 4.2 background music / audio overlay track: layer dict and filter
  builder first (pure functions, typed, mypy-clean), UI second.
- Volume, fade in/out, loop-to-length, duck-original toggle.
- **Exit:** audio layer renders identically in preview and export (the
  standing parity rule); mute + audio-only paths regression-tested.

### M4 — v1.10.1: Release-gates hardening (process milestone, any time) — P1 / M

- `docs/RELEASE.md` gains the v1.8.0 postmortem checklist: codesign verify,
  wheel import smoke on clean venv, arch check for bundled binaries,
  Store-cert notes dry run.
- CI: artifact-level smoke test installs the built wheel/exe and runs
  `--selftest` before any publish step.
- S8: pin CI tools; `pip-audit` job.
- **Exit:** a release can be executed end-to-end from the checklist by
  someone tired at midnight without creative thinking.

### M4.5 — v1.9.x: Editor layout — P1 / L

The interaction problem behind M5's refactor, split out because it is
worth shipping on its own. `ui/trim_tab.py` stacks every panel in one
`CTkScrollableFrame`, preview included, so the video scrolls out of view
exactly when a caption or sticker is being positioned — see
[`UX-SWEEP.md`](UX-SWEEP.md) U1.

Six layout directions are drawn up as a design canvas (pinned preview,
rail + inspector, timeline dock, split compare, guided steps, focus +
command palette), each with its trade-off noted. Pick one before the M5
extraction starts — the split is much cheaper when the target layout is
known.

- **Exit:** the preview never leaves the viewport during a normal edit;
  the default window size fits the chosen layout's primary task (U5).

### M5 — v2.0.0: UI test harness + monolith split — P2 / L

- xvfb headless Tk on CI; 15–20 smoke tests on the highest-churn seams
  (snapshot/apply round-trip, preset revert logic, batch queue restore).
- P1 monolith split (trim_tab, video_player) as pure refactors with the new
  harness as the safety net.
- **Exit:** UI coverage exists on CI; the two files are under ~600 lines
  each or their extraction plan is demonstrably executed; zero behavior
  change (major bump is for the internal API the plugin docs now version).

### M6 — v2.1.0: Creation power pass — P2 / M–L

- ROADMAP 2.4 per-layer opacity; 2.5 slide-in/typewriter presets (data-driven
  registry); 2.8 Whisper word-level timestamps; 2.9 SRT round-trip export.
- 3.4 boomerang/reverse with the memory gate (perf P6).
- 4.3 silence-based auto-cut on the multi-range machinery.
- **Exit:** karaoke-style caption demo in the README GIF; every new
  expression builder has a parity test vs. preview math.

### M7 — v2.1.x: Target-size GIF export — P2 / L

- ROADMAP 3.5: iterative quality ladder to hit "under 8 MB for Discord";
  platform presets carry size budgets.
- **Exit:** reference clips converge in ≤2 attempts; ladder steps visible in
  the progress dialog; budget overshoot <5% on the test corpus.

### M8 — Distribution trust — P2 / budget-gated

- macOS notarization (paid Apple Developer account — the README's first-
  launch workaround goes away; this is the single biggest trust/UX win
  available).
- Windows signing: EV/OV cert or Azure Trusted Signing (ROADMAP 6.2).
- S5 pinned digests for the in-app FFmpeg fetch.
- **Exit:** clean first launch on macOS 15+ with zero settings trips;
  SmartScreen warning eliminated or documented as residual.

### M9 — v2.2.0: Performance pass — P2 / M

- P3 preview/decode audit (backpressure, scrub cache, thumbnail/waveform
  disk cache).
- P4 lazy-import sweep + cold-start measurement.
- Debug-tab export stats line (suggestion 5) to make the wins quotable.
- **Exit:** measured numbers in release notes: cold start, project re-open,
  10s-clip export before/after.

### M10 — v2.3.0: Modern formats — P3 / M

- ROADMAP 3.8 WebP/APNG sibling formats with encoder probing; 3.7
  transparent GIF (chroma-key + reserve_transparent).
- **Exit:** WebP export ≥40% smaller than GIF at matched visual quality on
  the reference set; options hidden when encoders absent.

### M11 — v2.4.0: Capture+ — P3 / M

- ROADMAP 4.6 region and multi-monitor screen capture (monitor picker,
  rubber-band region select).
- Investigate (don't promise) system-audio loopback per platform.
- **Exit:** region capture ships on all three desktop OSes; loopback
  decision documented either way.

### M12 — v2.5.0: Plugin ecosystem v1 — P3 / M

- S4 plugin consent dialog + disable toggles.
- Plugin API stability policy + versioned docs; one example plugin repo
  (e.g. a custom export-preset pack) as the reference implementation.
- **Exit:** a third party can build, install, and consent-gate a plugin
  using only the public docs.

### M13 — v2.6.0: Platform breadth — P3 / S–M

- ROADMAP 4.4 surface TikTok / Twitch / Vimeo / Streamable chips (the
  documented four-line recipe per platform).
- Clipboard-monitor mode (optional, off by default): offer to kidnap a
  video URL when one lands on the clipboard.
- **Exit:** each new platform has detection tests + chip + share target
  where applicable.

### M14 — v2.7.0: Project format v2 — P3 / M

- `.vidkid` schema v2 with a real migration framework (v1 files load
  through an upgrader); media-embed option (single-file portable project).
- **Exit:** every v1 test fixture still opens; round-trip tests for the
  migration path.

### M15 — v2.8.0: Batch & queue depth — P3 / M

- P5 parallel batch encoding with hardware-encoder guard.
- Watch-folder mode for the batch queue (drop files in a folder, they
  process with the current preset).
- **Exit:** 8-clip batch wall-time reduced ≥35% on the reference machine;
  watch folder documented as power-user feature.

### M16 — v2.9.0: Accessibility & internationalization groundwork — P3 / M

- Keyboard-focus audit of every dialog; visible focus rings; screen-reader
  labels on the canvas-driven controls where Tk allows.
- String extraction pass (no translations yet — just make every user-facing
  string extractable).
- **Exit:** the full export flow is completable keyboard-only; zero
  hard-coded strings outside the string table.

### M17 — v3.0.0: Architectural inflection (decision milestone) — P3 / L

- Evaluate the ceiling of Tk/CustomTkinter for the editor's ambitions
  (timeline zoom, multi-track, scrub smoothness). Decision options: stay +
  deepen, adopt a canvas-based custom timeline, or evaluate another
  toolkit. This is a *written-decision* milestone, not a rewrite promise.
- ROADMAP 5.3 migrate off the `ffmpeg_backend` facade to a deprecation
  stub.
- **Exit:** an ADR in `docs/` records the decision and the criteria used.

### M18 — Continuous: Code health (never "done") — ongoing

- mypy allowlist expansion (ROADMAP 5.4): each new module ships typed; flip
  one existing `core/` module per release.
- Ruff rule adoption as its own PR (BLE001, I001, S110 — the ~215 known
  findings noted in `pyproject.toml`), never as a silent CI break.
- Test count is a vanity metric; the real gate is: every bug fix lands with
  the test that would have caught it.

### M19 — Continuous: Dependency & platform watch — ongoing

- yt-dlp cadence is the app's heartbeat; keep the in-app updater prominent
  and treat extractor-fix releases as potential patch triggers.
- Track ffmpeg, CustomTkinter (note the `>=5.2,<7.0` pin), Pillow, and
  Python 3.14 packaging changes; track macOS/Windows signing policy shifts
  that affect the trust milestones (M8).

### M20 — Someday/maybe (parking lot, explicitly unscheduled)

- Karaoke word-highlight preset (consumes 2.8 output).
- Chroma-key green-screen removal beyond GIF transparency.
- Soft-subtitle muxing (`-c:s mov_text`) after SRT round-trip lands.
- Auto-reframe with subject tracking (uses the OpenCV tracker already
  bundled).
- Linux Wayland screen-capture path when mss/portals stabilize.
- Mobile companion or web demo — only if the architecture decision (M17)
  makes it cheap.

---

## 5. Sequencing logic, in one paragraph

M1–M2 close every known security and robustness debt while it's cheap.
M3–M7 stack user-visible creation power on the hardened base. M8 buys trust
the moment budget allows because it de-risks every download metric. M5 and
M9 are deliberately placed *before* the format/capture/ecosystem expansion:
tests and perf headroom are what make M10–M16 boring instead of heroic.
M17 is the honest admission that a Tk app has a ceiling, scheduled early
enough that the decision informs — rather than follows — the parking lot.

---

*Update this file in the same PR that ships or re-scopes a milestone, the
same discipline BLUEPRINT.md and ROADMAP.md ask for.*
