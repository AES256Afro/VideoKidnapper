# 05 — Errors that survive being missed

**Effort:** S · **Status:** open · **Needs:** nothing

## Problem

There are **75 `_notify()` calls** across `ui/`, and `_notify` routes to
the `Toast` in the status bar (`ui/widgets.py:254`). A toast is
transient by design.

So an export failure that appears while you are looking at the preview
is simply gone. The only remaining record is the Debug tab, which most
users have no reason to ever open — and which, since #103, is not even
built until something needs it.

That is a poor trade for the one class of message users most need to
keep: the failures. "Exported 3 clips" can vanish safely; "Clip 2 failed:
no space left on device" cannot.

## Concept

Failures accumulate somewhere they can be found later; successes stay
transient.

## How it could work

- A small persistent indicator in the status bar — `⚠ 1 problem` —
  appearing only when something has actually failed.
- Clicking it opens the detail: what failed, when, and the underlying
  message that today only reaches the Debug tab.
- Clears on acknowledgement, or when the next export succeeds.
- `_notify` already takes a level (`"error"`, `"warn"`, `"success"`,
  `"info"`), so the routing rule already exists in the call sites —
  errors and warnings persist, the rest do not.

## Trade-offs

- Needs a severity policy, or it becomes a nag. "Could not read
  clipboard image" is not worth a persistent badge; a failed export is.
- Overlaps with the Debug tab. Either this becomes the friendly front
  door to the same log, or the two drift apart — worth deciding rather
  than discovering.

## Done when

An export that fails while the user is looking elsewhere is still
discoverable a minute later, without opening the Debug tab.
