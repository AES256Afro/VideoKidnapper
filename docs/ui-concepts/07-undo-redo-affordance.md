# 07 — Undo/redo you can see

**Effort:** S · **Status:** open · **Needs:** nothing

## Problem

Undo and redo work and are bound on every platform since 1.8.2 — Ctrl+Z
/ ⌘Z, Ctrl+Y, Ctrl+Shift+Z. But there is **no button anywhere**:
searching `ui/*.py` for an undo or redo widget returns nothing.

So the feature is invisible. Someone who does not already expect it will
not discover it, and someone who does still has no way to see how far
back the stack goes or what the next undo will actually revert. After a
flurry of caption edits, "how many times do I press this" is guesswork.

The shortcuts overlay (`?`) documents the keys, which helps only people
who already went looking.

## Concept

Toolbar undo and redo buttons that also show what they will do.

## How it could work

- Two buttons in the header, greyed when their stack is empty — the
  empty state alone communicates that history exists.
- Tooltip or label naming the step: *Undo — add caption*.
- Optionally a dropdown listing recent steps, so several can be undone
  at once.
- `trim_tab` already tracks `_restoring` to suppress recording during
  bulk widget resets, so there is an existing notion of what counts as
  one user action to hang labels on.

## Trade-offs

- The stack currently records coarse snapshots. Labelling steps means
  naming the actions that create them, which is a small change spread
  across many call sites rather than one contained edit.
- Header space is finite; this competes with the project and setup
  controls already there.

## Done when

Undo is discoverable without reading the shortcuts overlay, and the
control says what it is about to undo.
