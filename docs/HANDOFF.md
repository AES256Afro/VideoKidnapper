# Handoff — Security hardening session (2026-08-28)

State of the tree after a working session on the M1 security/robustness
milestone from [`docs/MILESTONES.md`](MILESTONES.md). Written so the next
session (human or agent) can pick up mid-stream without re-auditing.

## Where things stand

- Test suite: **560 passed, 1 skipped** (baseline at session start was
  543 passed, 1 skipped). All work below is uncommitted on `main` — run
  `git status` / `git diff` to see it.
- Branch point: v1.8.1 (`303f9f4`).

## Completed in this session

### S2 — `tempfile.mktemp` eradicated (done)

- `_mkstemp_path(suffix)` now lives in
  `videokidnapper/core/ffmpeg/_internals.py` (mkstemp + close + return Path).
- `encode.py` deleted its local copy and imports the shared one;
  `concat.py` (concat list file) and `core/whisper_captions.py` (WAV
  scratch file) switched from `mktemp` to the helper.
- Anti-regression: `tests/test_tempfile_hygiene.py` greps the whole
  package tree and fails if `mktemp(` reappears anywhere.

### S3 — Elevated-terminal quoting hardened (done)

- `videokidnapper/utils/prereq_check.py` gained a documented quoting
  contract (comment block above `build_install_commands`):
  - Windows: command is Base64-encoded and run via PowerShell
    `-EncodedCommand` (`_powershell_encoded`) — no quoting layer can
    reinterpret it.
  - macOS: `shlex.quote` for bash, then AppleScript string-literal
    escaping (`_applescript_do_script`).
  - Linux: `shlex.quote` for bash.
- `tests/test_admin_terminal.py` asserts the emitted bytes for a hostile
  payload on all three platforms (spy-Popen; macOS/Linux tests reverse
  the quoting with `shlex.split` to prove the payload arrives as one
  inert argument).

### S1 — Project-file filter injection: `position` field closed (done)

- **Found a real residual injection** of the same class as the v1.8.1
  colour bug: `layer["position"]` was interpolated bare into
  `x=…:y=…` in `_build_drawtext_filter` (`core/ffmpeg/filters.py`).
  A crafted `.vidkid` could set `position` to `0:0,movie=/etc/passwd`
  and inject arbitrary filter graph (file disclosure via `movie=`).
- Fix: `sanitize_position_expr()` in `videokidnapper/utils/ffmpeg_escape.py`
  — allowlists the two legitimate shapes (the 7 `config.POSITION_MAP`
  preset expressions, and numeric `x:y` drag pairs); anything else falls
  back to the default bottom-center. Validation, not escaping, same
  philosophy as `sanitize_color`.
- Also fail-soft coercions in `filters.py` so corrupt projects can't
  abort an encode: `fontsize`, `boxborderw`, `start`/`end`/`fade`,
  corrupt keyframes (fall back to static position), overlay
  scale/opacity/timing, drag coords.
- `tests/test_position_injection.py`: 9 tests — all presets pass through,
  15 injection payloads rejected, corrupt numbers fail soft, keyframed
  paths still compile.

### Audit conclusions (no action needed)

- `text` → `escape_drawtext_value` ✓; colours → `sanitize_color` ✓;
  keyframes compile to formatted floats only ✓; `_find_font_path` is a
  lookup confined to the fonts dir ✓; image overlay `path` becomes an
  ffmpeg `-i` input, which is inherent to the project-file feature.

## In progress when this handoff was written

### S6 — Open/Reveal path validation (NOT STARTED, call sites mapped)

Plan: create `videokidnapper/utils/reveal.py` with two helpers —
`open_file(path)` and `reveal_in_file_manager(path)` — that validate
(non-empty, resolves to an existing local path, no URI scheme) then
dispatch per-OS. Replace all six scattered call sites:

- `ui/history_tab.py:144-158` (`_open`, `_reveal`)
- `ui/batch_export_tab.py:460-477` (`_reveal_output`, `_open_source_folder`)
- `ui/batch_export_tab.py:688-697` (`_open_output_folder`)
- `ui/export_dialog.py:148-154` (`_open_folder`)
- `ui/trim_tab.py:752-760` (`_play_in_system` — note its Darwin branch)
- `ui/export_options.py:417-425` (`_open_folder`)

Motivation: paths come from the user-writable settings JSON; a tampered
file currently gets handed straight to `xdg-open`/`explorer`/`open`.

## Remaining queue (from MILESTONES.md, in order)

1. **S6** above.
2. **ROADMAP 1.4** — disk-space/writability preflight before export:
   `shutil.disk_usage` vs `utils/size_estimator.py` estimate, warn-don't-block.
3. **M2 / ROADMAP 1.5** — stale temp-file sweep on startup (palette PNGs,
   overlay intermediates, screen-record scratch), files older than N days.
4. **M2 / ROADMAP 1.7** — ffmpeg `-progress` parse hardening: malformed
   lines / `N/A` must degrade to an indeterminate bar, not a stuck one
   (`core/ffmpeg/_internals.py::_parse_progress`).
5. **M0** — reconcile `docs/ROADMAP.md` sequencing with v1.8.x reality
   (its v1.3–v1.5 section is stale; several listed items have shipped).
6. **Final** — full test run, CHANGELOG entry (Unreleased → v1.8.2
   Security/Fixed), update MILESTONES.md statuses.

## Environment notes

- Tests run with the Kimi managed Python; this session installed
  `pytest`, `customtkinter`, `mss`, `yt-dlp` into it. Command:
  `cd /Users/chris/Projects/VideoKidnapper && python -m pytest tests/ -q`
- One skipped test is pre-existing (not from this session).
- `tests/test_tempfile_hygiene.py` resolves the temp dir on both sides
  because `/var` is a symlink to `/private/var` on macOS — don't
  "simplify" that away.

## Files touched this session

Modified: `core/ffmpeg/_internals.py`, `core/ffmpeg/concat.py`,
`core/ffmpeg/encode.py`, `core/ffmpeg/filters.py`,
`core/whisper_captions.py`, `utils/ffmpeg_escape.py`,
`utils/prereq_check.py`.
New: `tests/test_tempfile_hygiene.py`, `tests/test_admin_terminal.py`,
`tests/test_position_injection.py`, `docs/MILESTONES.md`, this file.
