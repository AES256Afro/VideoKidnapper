# 04 — Time remaining on exports

**Effort:** S · **Status:** open · **Needs:** nothing

## Problem

`grep -rn "eta\|remaining"` finds nothing in the package. The export
dialog has a percentage bar (`ui/export_dialog.py:67`) and a status
line, and that is all.

A percentage answers "how far", not "how long". At 40% you cannot tell
whether the next step is ten seconds or four minutes, so a slow export
is indistinguishable from a stuck one — which is the same perception
problem `MILESTONES.md` P7 records for malformed progress output.

The data is already being parsed. `core/ffmpeg/_internals.py`
`_parse_progress` reads FFmpeg's `time=` field on every stderr line, so
elapsed wall-clock and encoded-media time are both in hand; the ratio
is encode speed.

## Concept

Show remaining time and encode speed next to the progress bar.

## How it could work

- `_parse_progress` already computes `current / duration`. Track wall
  time alongside it and derive `speed = media_seconds / wall_seconds`.
- Show `about 1m 20s left` plus `1.4× realtime`.
- Smooth over a rolling window. A raw instantaneous estimate jumps
  around badly at the start of an encode and reads as unreliable.
- Suppress the estimate for the first couple of seconds rather than
  showing a wild number, and fall back to elapsed-only when FFmpeg's
  output is unparseable — an indeterminate bar is honest; a stuck one
  is not.
- The GIF path runs two passes (`palettegen` then `paletteuse`), so the
  estimate must account for both or explicitly say which pass it is on.

## Trade-offs

- An ETA that swings wildly is worse than no ETA. The smoothing is the
  actual work here, not the arithmetic.
- Hardware encoders vary in throughput far more than libx264, so early
  estimates on those will be rougher.

## Done when

A long export shows a stable, shrinking estimate, and an unparseable
progress stream degrades to elapsed time rather than a frozen bar.
