# UI concepts

Ten concepts for improving the VideoKidnapper interface, one per file so
each can be read, argued with, or picked up on its own.

Written against `main` at `b8a90f2` (2026-09-02). Every claim carries a
file reference — disagree with the reasoning, not with a re-derivation.

| # | Concept | Effort | Status |
|---|---|---|---|
| [01](01-pinned-preview.md) | Pin the preview | L | open |
| [02](02-live-export-preview.md) | Live export preview | M | open |
| [03](03-layer-list.md) | Layer list with visibility and solo | M | open |
| [04](04-export-eta.md) | Time remaining on exports | S | open |
| [05](05-persistent-problems.md) | Errors that survive being missed | S | open |
| [06](06-theme-without-restart.md) | Theme switching without a restart | M | open |
| [07](07-undo-redo-affordance.md) | Undo/redo you can see | S | open |
| [08](08-command-palette.md) | Command palette | M | open |
| [09](09-range-queue-reorder.md) | Range queue: reorder and label | S | open |
| [10](10-sizing-and-focus.md) | Window sizing and keyboard focus | S | open |

An eleventh — animating stickers in the preview — shipped in #103 while
these were being written, closing the last preview/export parity gap.

---

## What "best quality UI" actually takes here

Three things, in order. The first is a decision, the second is work, and
the third is a limit worth knowing about before either.

### 1. Fix the layout before polishing anything on top of it

`ui/trim_tab.py:84` puts every panel — **including the preview** — inside
one `CTkScrollableFrame`. Editing a caption scrolls the video off the
top of the window, so you lose sight of the thing you are positioning.
The TOOLS jump-dock added in 1.8.0 makes that scrolling quicker to
navigate rather than unnecessary.

Nothing else on this list pays off properly until that is fixed.
Concepts 02 and 03 both assume a preview you can see while working, and
concept 01 needs concept 10's sizing to have room to exist. Six layout
directions are drawn up as a
[design canvas](https://claude.ai/code/artifact/ef984929-c841-4783-ba25-8b9e52904f4b);
picking one is a decision, not a refactor, and it should be made before
`MILESTONES.md` M5 starts pulling `trim_tab.py` apart — the extraction
is far cheaper when the target shape is known.

### 2. Then buy trust, cheaply

Concepts 04, 05, 07 and 09 are all small, independent, and about the
same thing: the app knowing more than it tells you. There is no ETA
anywhere in the package, 75 `_notify()` calls all route to a transient
toast, undo works but has no visible control, and the queue whose order
determines concat output cannot be reordered. Each is a day or less.

### 3. Know where the ceiling is

CustomTkinter is a Tk wrapper, and some quality ceilings come from that
rather than from anything this codebase did:

- **Theme changes need a restart.** `ui/theme.py:6` — "ctk widgets bake
  their colors at construction". Concept 06 works around it; it does not
  remove the cause.
- **No HiDPI handling.** Nothing calls `tk scaling` or CustomTkinter's
  widget-scaling API, so rendering is whatever Tk defaults to per
  platform.
- **No accessibility layer.** Tk exposes no accessibility tree, so
  screen readers get nothing regardless of how the widgets are arranged.
- **No animation primitives.** Every transition would be hand-rolled on
  `after()` ticks.
- **Widgets are canvas-drawn**, so text rendering, focus rings and
  scrolling feel do not match the host platform.

Within those limits the app can be genuinely good — dense, fast,
consistent, keyboard-driven. What it cannot be is indistinguishable from
a native or web-grade editor.

**The recommendation: stay on CustomTkinter.** Do 01 and 10 together,
then 04, 09, 05, 07 in whatever order suits. That is where the quality
is, and it costs weeks rather than a rewrite.

Moving the UI layer (PySide6/Qt, or a webview front-end over the
existing Python core) would lift every ceiling above and cost a
substantial rewrite of `ui/` — roughly 8,000 lines. It is a real option
because the core is already cleanly separated: `core/` and `utils/` are
pure and well tested, and `ui/` talks to them through narrow seams. But
it is only worth it if "best quality" means competing with native
editors, and nothing in the current feedback suggests that is the goal.
Revisit if the layout work lands and the interface still feels limited
by the toolkit rather than by the design.
