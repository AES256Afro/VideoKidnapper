# 08 — Command palette

**Effort:** M · **Status:** open · **Needs:** nothing

## Problem

The app documents 19 shortcuts in its overlay registry
(`ui/shortcuts_dialog.py`) and spreads a growing set of features
across a tool dock, four tabs, several collapsible panels and a
right-click menu. Finding a rarely-used action means remembering which
of those it lives in.

That tension gets worse with every feature, and the roadmap has many
queued (`MILESTONES.md` M6, M7, M10, M11).

The app's actual loop — grab a clip, caption it, post it — is fast and
repetitive, which is precisely the shape a palette suits.

## Concept

Ctrl/⌘K opens a searchable list of every action, with its shortcut.

## How it could work

- One registry of commands: label, optional shortcut, handler,
  availability predicate. The shortcuts overlay
  (`ui/shortcuts_dialog.py`) already keeps a static table of label and
  description — a command registry is that table with a callable
  attached, and both surfaces could then read from one source.
- Fuzzy match on label, most-recent-first.
- Show the bound shortcut beside each entry, which teaches the keys as
  a side effect.
- Context-sensitive availability: no *Export* entry with no video open.

## Trade-offs

- **Only pays off if it covers everything.** A palette that knows about
  eight of forty actions trains people not to use it, and is then worse
  than no palette.
- Duplicates navigation that already exists, so it must be genuinely
  faster than the dock, not merely another way in.
- The `?` overlay and the palette would overlap; likely the overlay
  becomes a view of the same registry rather than a separate table.

## Done when

Every action reachable through the UI is reachable through the palette,
and the shortcuts overlay is generated from the same registry.
