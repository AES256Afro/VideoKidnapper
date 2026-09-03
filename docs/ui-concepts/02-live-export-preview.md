# 02 — Live export preview

**Effort:** M · **Status:** open · **Needs:** 01

## Problem

The canvas shows the source frame. What lands on disk is something else
— a 480px, 15fps, 128-colour GIF with Bayer dithering, or an H.264 MP4
at a chosen CRF. Those are different pictures, and the difference is
exactly what people get wrong: banding in gradients, dither crawl on
flat colour, text that was crisp at source and mushy at 480px.

Today the only way to find out is to run the export and look at the
file. On a long clip that is a 90-second round trip per guess.

The pieces already exist. `utils/size_estimator.py` predicts output
size, and `core/preview.py` already renders single frames.

## Concept

A second preview pane showing the real encoded result — same palette,
same dither, same scale, same frame rate — beside the source.

## How it could work

- Encode a short window around the playhead (say 1–2 seconds) through
  the actual export filter chain, at export settings, and show it.
- Refresh on settings change, throttled — or behind an explicit
  **Refresh preview** button, which is honest about the cost.
- Reuse the existing filter builders so the preview cannot drift from
  the export; anything else recreates the parity problem the project
  has been careful about elsewhere.
- Pair it with the existing size estimate, so quality and size are
  answered in the same place.

## Trade-offs

- A live second render costs real CPU on every settings change. Almost
  certainly needs throttling, a short window, or manual refresh.
- The GIF path runs `palettegen` over the whole clip; a windowed
  preview would use a local palette and could differ slightly from the
  final file. Worth stating in the UI rather than hiding.
- Doubles the pixels on screen — needs concept 01's layout to have
  anywhere to put it.

## Done when

Changing preset, width, fps or dither visibly changes the preview, and
the shipped file matches what the preview showed.
