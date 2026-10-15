# 09 — Range queue: reorder and label

**Effort:** S · **Status:** open · **Needs:** nothing

## Problem

`ui/batch_queue.py` has no reordering — no move-up, move-down or drag.

That matters more than it sounds, because when *Concat ranges* is on,
**the queue order is the output order**. Getting the sequence wrong
today means deleting rows and re-adding them in the right order, and
re-adding means re-finding each in-point and out-point.

Rows are also hard to tell apart. A queue of five entries distinguished
only by timecodes gives no sense of what is actually in each clip.

`MILESTONES.md` lists this as ROADMAP 4.8 in the "small UX wins" queue.

## Concept

Drag to reorder, and make each row identifiable at a glance.

## How it could work

- Drag-and-drop rows, or move-up/move-down buttons — the latter is
  cheaper and keyboard-accessible, and could ship first.
- A thumbnail per row from its in-point. `core/preview.get_frame_at`
  already extracts a frame at a timestamp, and the thumbnail strip
  already renders them.
- Duration alongside the timecodes, since that is what people actually
  reason about when sequencing.
- Optional per-range label, which would also give the concat progress
  dialog something better than "Clip 2/5" — another item in the same
  roadmap queue.

## Trade-offs

- Thumbnails mean one extra FFmpeg call per range at queue time. Cheap,
  but it should be async so adding a range stays instant.
- Drag-and-drop inside a `CTkScrollableFrame` needs care not to fight
  the scroll.

## Done when

A concat sequence can be rearranged without deleting anything, and
queue rows are distinguishable without reading timecodes.
