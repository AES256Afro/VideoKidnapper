# 01 — Pin the preview

**Effort:** L · **Status:** open · **Blocks:** 02, 03 · **Needs:** 10

## Problem

`ui/trim_tab.py:84` builds the whole editor as one scroller:

```python
self.body = ctk.CTkScrollableFrame(self, ...)
```

and the preview is a child of it (`trim_tab.py:168`, `height=320`), along
with Source, Timeline, Ranges, Text, Overlays, Options and Export.

So reaching the Text or Overlays controls scrolls the video off the top
of the window. That inverts the core feedback loop: captions and
stickers are positioned **visually**, and the moment you adjust one is
exactly the moment you can no longer see what you are adjusting.

The "TOOLS" jump-dock added in 1.8.0 (`_build_feature_dock`) is a
response to the same problem — it makes the scrolling faster to
navigate, rather than unnecessary.

At the default 1000×700 window (`config.py:52`) there is not enough
height for a 320px preview, a timeline, and any panel at once, which is
why this concept and [10](10-sizing-and-focus.md) travel together.

## Concept

The preview and timeline occupy fixed space. Only the panels scroll.

## How it could work

Six directions are drawn up as a
[design canvas](https://claude.ai/code/artifact/ef984929-c841-4783-ba25-8b9e52904f4b),
from smallest change to largest:

- **Pinned header** — preview + timeline become a fixed region above a
  scrolling panel area. Keeps most of `trim_tab.py` intact.
- **Rail + inspector** — icon rail picks a mode, centre stage never
  moves, right-hand inspector shows only the selected thing.
- **Timeline dock** — layer tracks along the bottom, NLE-style; caption
  and sticker timing become drag operations rather than numeric fields.
- **Split compare**, **guided steps**, **focus + command palette** — see
  the canvas.

Pick one before `MILESTONES.md` M5 begins extracting `trim_tab.py` and
`video_player.py`. The split is much cheaper with a known target shape,
which is why `MILESTONES.md` now carries M4.5 ahead of it.

## Trade-offs

- The panel area gets short on a 700px-tall window — hence concept 10.
- Rail + inspector and timeline dock both need a real selection model,
  which does not exist today.
- A timeline dock needs a track widget; CustomTkinter has none, so it
  would be canvas-drawn like the existing thumbnail strip.

## Done when

The preview never leaves the viewport during a normal edit, and the
default window size fits the chosen layout's primary task.
