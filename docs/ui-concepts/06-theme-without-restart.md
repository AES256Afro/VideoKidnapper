# 06 — Theme switching without a restart

**Effort:** M · **Status:** open · **Needs:** nothing

## Problem

`ui/theme.py:6` states it plainly:

> Tokens are selected once at import time from the dark or light palette
> based on `settings.get("theme")`. Changing the theme requires a restart
> because ctk widgets bake their colors at construction — reconfiguring
> them live is brittle and not worth the complexity.

And `app.py:211` labels the control "(takes effect on restart)".

The reasoning was sound when written. The cost is that switching theme —
the single most visible preference in the app — means losing your
session: the loaded video, trim range, captions and undo history all go.
Most people will simply never switch, which makes the light palette
largely dead code.

## Concept

Apply a theme change immediately, without discarding the session.

## How it could work

Two honest routes, in increasing cost:

1. **Preserve and relaunch.** Keep the restart, but make it invisible:
   autosave the session (`utils/project_files.py` already has atomic
   autosave and crash recovery), relaunch, and restore. The mechanism
   already exists for crash recovery — this reuses it for a deliberate
   restart. Cheap, and removes the actual pain even though the process
   really does restart.
2. **Live re-theming.** Walk the widget tree and reconfigure colours on
   theme change. This is what `theme.py` calls brittle, and it is right:
   every widget would need to declare which tokens it used, and any
   widget that missed one would be visibly wrong.

Route 1 is the recommendation. Route 2 is the "correct" answer and is
not worth it inside CustomTkinter.

## Trade-offs

- Route 1 is a workaround, not a fix — the app still restarts, and any
  state not covered by the project file is still lost.
- Route 2 risks a half-themed window, which looks worse than a restart.
- Either way this is a ceiling imposed by the toolkit, not the codebase;
  see the README's note on where CustomTkinter's limits are.

## Done when

Switching theme keeps the loaded video, trim range and overlays, and
the user is not asked to restart manually.
