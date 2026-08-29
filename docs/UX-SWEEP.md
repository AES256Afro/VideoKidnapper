# Usability sweep — 2026-08-29

A pass over the editor's interaction design, done against `main` at
v1.8.1 by reading `ui/` and running the app. Findings are ordered by how
much they cost a user, not by how hard they are to fix. Each names the
evidence so the next person can disagree with the reasoning rather than
re-derive it.

Companion to [`MILESTONES.md`](MILESTONES.md) (sequencing) and
[`ROADMAP.md`](ROADMAP.md) (features). Six layout directions responding
to U1 are drawn up as a design canvas — see the "Editor layouts" note in
the milestone entry for M5.

---

## U1 — The preview scrolls out of view while you edit — P1

**The single biggest interaction problem in the app.**

`ui/trim_tab.py:78` puts everything in one scroller:

```python
self.body = ctk.CTkScrollableFrame(self, ...)
```

and the video preview is a child of it (`trim_tab.py:159`, `height=320`).
Source, Preview, Timeline, Ranges, Text, Overlays, Options and Export are
stacked in that single column, so reaching the Text or Overlays panel
scrolls the video off the top of the window.

That inverts the core feedback loop: captions and stickers are positioned
*visually*, and the moment you adjust one is exactly the moment you can no
longer see what you are adjusting. At the default 1000×700 window there is
not enough height for both.

The "TOOLS" jump dock added in 1.8.0 (`_build_feature_dock`) is a
workaround for the symptom — it makes the scrolling faster to navigate
rather than unnecessary.

**Direction:** the preview and timeline should occupy fixed space; only
the panels should scroll. Anything from a pinned header (smallest change,
keeps most of `trim_tab.py`) to a two-pane or timeline-dock layout solves
it. This is the motivation for the M5 layout work.

## U2 — macOS has no working keyboard shortcuts — P1 — FIXED

All 32 accelerators were bound as `<Control-...>` only. Tk treats Ctrl and
Cmd as separate modifiers, so ⌘O / ⌘S / ⌘E did nothing on macOS while the
shortcuts overlay advertised "Ctrl+O". Notable because macOS is the
platform that just absorbed a whole release cycle of distribution work.

Fixed: accelerators bind under both modifiers, and the overlay renders
`⌘⇧S` on darwin. See `_bind_accel` in `app.py`.

## U3 — Animated stickers were offered but broke the export — P1 — FIXED

`SUPPORTED_IMAGE_EXTS` (`ui/image_layers.py:51`) has always listed `.gif`
and `.webp`, so the file picker offered them — and choosing one aborted
the export, because the encoder passed every overlay `-loop 1` (an
image2-demuxer option ffmpeg rejects for a GIF).

A picker that offers a file type the pipeline cannot accept is a
usability bug before it is a technical one. Fixed with real animated
sticker support; the overlay row now also labels animated files, because
a path does not tell you whether something moves.

## U4 — The preview cannot show an animated sticker — P2

The canvas composites overlays with Pillow (`ui/video_player.py`), one
frame per layer, so an animated sticker previews as its first frame while
the export animates. The app otherwise holds a strict preview/export
parity rule, and this is now the one place it does not hold.

Mitigated for now by the "● animated · N frames" badge, which at least
makes the difference visible. A real fix advances the sticker's frame
with the playhead — cheap, since Pillow already has the frames decoded.

## U5 — Default window is too small for the layout — P2

`WINDOW_SIZE = "1000x700"`, `MIN_WINDOW_SIZE = (680, 480)`
(`config.py:52`). With a 320px preview, a timeline, and eight stacked
panels, 700px of height cannot show the video and any control at the same
time — U1 is partly a consequence of this. At 480px minimum height the
preview alone is most of the window.

Whatever layout M5 lands on should come with a default sized to fit its
own primary task, and a minimum that keeps the preview and one panel
visible together.

## U6 — Destructive and slow actions need clearer feedback — P3

Worth checking as a group during the M5 work: what "Stop" looks like
mid-export now that cancellation is prompt (1.8.1) rather than hanging;
whether removing a text or image layer is undoable in a way users notice;
and whether the batch queue makes it obvious which row is running.

Not investigated in depth this pass — listed so the next sweep starts
here rather than rediscovering it.

---

## What shipped from this sweep

| Finding | Status |
|---|---|
| U2 macOS accelerators | fixed |
| U3 animated stickers offered but broken | fixed |
| U4 preview parity for animated stickers | badge only; frame stepping open |
| U1 preview scrolls away | six layout directions drafted; not implemented |
| U5 window sizing | open, tied to U1 |
| U6 feedback on slow/destructive actions | open |
