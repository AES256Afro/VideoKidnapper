# 10 — Window sizing and keyboard focus

**Effort:** S · **Status:** open · **Pairs with:** 01

## Problem

Two unglamorous things that quietly cap the quality of everything else.

**Sizing.** `config.py:52`:

```python
WINDOW_SIZE = "1000x700"
MIN_WINDOW_SIZE = (680, 480)
```

A 320px preview plus a timeline plus one panel does not fit in 700px of
height, which is half of why the editor scrolls at all
([01](01-pinned-preview.md)). At the 480px minimum the preview alone is
most of the window, and the app is effectively unusable at its own
stated floor.

**Focus.** There are **3 `focus_set` calls in the entire UI**. Tab order
is therefore whatever Tk infers from widget creation order, which is not
the reading order in a layout built from nested frames. There are no
visible focus rings, so keyboard-only operation means navigating blind.

This is also the accessibility floor: Tk exposes no accessibility tree,
so focus order and visible focus are most of what can be offered.

## Concept

Size the window for its real task, and make keyboard navigation
deliberate.

## How it could work

- Set the default to fit whichever layout [01](01-pinned-preview.md)
  adopts — measured against the actual built layout, not guessed.
- Raise the minimum to whatever keeps the preview and one panel visible
  together, and let the layout degrade honestly below that rather than
  clipping.
- Persist window geometry between sessions; `utils/settings.py` already
  stores preferences atomically.
- One pass over tab order in the editor: explicit `takefocus` where the
  default is wrong, a sensible order through the panels, Escape and
  Return behaving consistently in dialogs.
- A visible focus indicator. CustomTkinter does not provide one, so this
  means a border token applied on `<FocusIn>` — small, but it has to be
  done deliberately per widget class.

## Trade-offs

- Raising the minimum window size excludes genuinely small screens.
  Worth checking against real display sizes before picking a number.
- Focus work is invisible when done well, which makes it easy to skip
  and easy to regress. Worth a couple of smoke tests in the harness
  `MILESTONES.md` M5 proposes.

## Done when

The app opens at a size where the preview and controls are usable
together, remembers where it was, and can be driven from the keyboard
with the focused control always visible.
