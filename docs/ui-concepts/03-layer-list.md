# 03 — Layer list with visibility and solo

**Effort:** M · **Status:** open · **Needs:** 01

## Problem

Text and image layers exist only as stacked editor panels. There is no
visibility control anywhere in `ui/text_layers.py` or
`ui/image_layers.py` — every layer is always on.

With four captions and two stickers there is no way to check one
against the frame, temporarily hide a sticker covering the subject, or
see the stacking order at a glance. The only way to evaluate one layer
is to delete the others and undo.

The canvas already supports direct manipulation — `video_player.py`
carries drag state for both text and image layers, with snapping via
`utils/snap.py` — so the missing piece is a list, not interaction.

## Concept

One list of all overlays, in z-order, with an eye toggle per row and a
solo control.

## How it could work

- A single panel listing text and image layers together, since they
  share a canvas and a stacking order.
- Eye icon toggles visibility; solo hides everything else temporarily.
- Selecting a row selects the layer on canvas, and vice versa — this is
  the selection model concept 01's inspector layouts need anyway.
- Drag to reorder, which is also how you fix z-order today (you cannot).

## Trade-offs

- **Visibility is export-affecting state.** A hidden layer must not
  render, which means it has to round-trip through `.vidkid`
  (`utils/project_files.py`) and participate in undo. Solo is transient
  and must *not* persist — mixing them up would silently drop layers
  from someone's export.
- Merging two panels into one list is a real change to two of the more
  complex UI files.

## Done when

A layer can be hidden and shown without deleting it, the state survives
save and reload, and solo never leaks into an export.
