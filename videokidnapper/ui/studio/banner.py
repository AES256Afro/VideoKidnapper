# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""The inline banner: questions asked inside the main window.

VideoKidnapper is one window with no popups. Anything that needs an
answer (recover unsaved work? save before closing? restart for the new
theme?) is asked in a slim bar that floats over the top edge of the
workspaces, directly under the header. Floating means showing or hiding
it never moves or resizes anything else.

Usage, from anywhere that can reach the app::

    prompt = app.banner.ask(
        "Save your project before closing?",
        buttons=[("Save", "primary", save),
                 ("Don't save", "secondary", discard),
                 ("Cancel", "ghost", None)],
        dismiss=cancel,          # shows a ✕; None hides it
        tone="warn",
    )
    prompt.close()               # take it away without an answer

Nothing blocks: ``ask`` returns at once and the button's callback runs
when it is clicked. One prompt shows at a time; the rest wait in order
and the next appears when the current one is answered or closed.

A prompt can also carry a determinate progress bar, for work the user
waits on (``app.banner.progress(...)`` then ``prompt.set_progress(0.4)``)
and can be reworded in place with ``prompt.update(...)``, so a download
can turn into "Restart to update" without a new prompt.

:class:`PromptQueue` holds the queue and the rules and has no widgets,
so it is tested without a display. :class:`InlineBanner` draws it.
"""

import tkinter as tk
from collections import namedtuple

import customtkinter as ctk

from videokidnapper.ui import theme as T
from videokidnapper.ui.studio.icons import glyph, icon_button, icon_font
from videokidnapper.ui.theme import button

#: How a prompt is colored. "info" for neutral news, "warn" when work could
#: be lost, "success" when something finished.
TONES = ("info", "warn", "success")
#: The bar is one line. More than three buttons would not fit beside the
#: message on a narrow window, and is too many choices for a bar anyway.
MAX_BUTTONS = 3

# "Leave unchanged" for Prompt.update, where None is a real value.
_KEEP = object()

BannerButton = namedtuple("BannerButton", "label variant command closes")


def _buttons(items):
    """Normalize ``(label, variant, command[, closes])`` tuples."""
    result = []
    for item in items or ():
        label, variant, command, *rest = item
        closes = bool(rest[0]) if rest else True
        result.append(BannerButton(str(label), variant, command, closes))
    if len(result) > MAX_BUTTONS:
        raise ValueError(f"a banner prompt has at most {MAX_BUTTONS} buttons")
    return result


def _fraction(value):
    if value is None:
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return 0.0
    if value != value:   # NaN
        return 0.0
    return max(0.0, min(1.0, value))


class Prompt:
    """One question in the banner, as returned by ``ask``.

    Keep it to close the prompt yourself, reword it, or move its progress
    bar. ``answer`` records how it ended: the label of the button that
    was clicked, ``"dismiss"`` for the ✕, or None if it was closed some
    other way (or is still open).
    """

    def __init__(self, owner, message, buttons, detail, dismiss, tone, progress, key):
        self._owner = owner
        self.message = str(message)
        self.detail = detail
        self.buttons = _buttons(buttons)
        self.dismiss_action = dismiss
        self.tone = tone if tone in TONES else "info"
        self.progress = _fraction(progress)
        self.key = key
        self.answer = None

    def __repr__(self):
        return f"<Prompt {self.message!r}>"

    @property
    def is_open(self):
        """Showing or waiting its turn."""
        return self._owner.current is self or self in self._owner.pending

    @property
    def showing(self):
        return self._owner.current is self

    @property
    def dismissable(self):
        """Whether the prompt has a ✕."""
        return self.dismiss_action is not None and self.dismiss_action is not False

    def close(self):
        """Take the prompt away without running any of its callbacks."""
        self._owner._close(self)

    def press(self, label):
        """Answer as if the button labelled ``label`` was clicked.

        Returns False when the prompt is closed or has no such button.
        """
        for item in self.buttons:
            if item.label == label:
                return self._owner._answer(self, item.command, item.closes, label)
        return False

    def dismiss(self):
        """Answer as if the ✕ was clicked; False when there is no ✕."""
        if not self.dismissable:
            return False
        action = self.dismiss_action if callable(self.dismiss_action) else None
        return self._owner._answer(self, action, True, "dismiss")

    def update(self, message=_KEEP, detail=_KEEP, tone=_KEEP, buttons=_KEEP,
               progress=_KEEP, dismiss=_KEEP):
        """Change the prompt in place; a showing prompt redraws at once."""
        if message is not _KEEP:
            self.message = str(message)
        if detail is not _KEEP:
            self.detail = detail
        if tone is not _KEEP:
            self.tone = tone if tone in TONES else "info"
        if buttons is not _KEEP:
            self.buttons = _buttons(buttons)
        if progress is not _KEEP:
            self.progress = _fraction(progress)
        if dismiss is not _KEEP:
            self.dismiss_action = dismiss
        # Only new buttons, a new ✕ or a new tone need a full redraw; a
        # progress tick should not recreate widgets several times a second.
        full = any(value is not _KEEP for value in (buttons, dismiss, tone))
        self._owner._changed(self, full=full)

    def set_progress(self, value, detail=_KEEP):
        """Move the progress bar (0 to 1), optionally with a new detail line."""
        self.update(progress=value, detail=detail)


class PromptQueue:
    """The banner's queue and rules, without any widgets.

    ``on_change(prompt, full)`` is called whenever what should be on
    screen changes: ``prompt`` is the one to show (None to hide) and
    ``full`` is False when only its text or progress moved.
    """

    def __init__(self, on_change=None):
        self.current = None
        self.pending = []
        self._on_change = on_change
        # While a button's callback runs: where the next follow-up goes.
        self._followups = None

    # -- asking ----------------------------------------------------------
    def ask(self, message, buttons=(), detail=None, dismiss=None, tone="info",
            progress=None, key=None, urgent=False):
        """Queue a prompt and return it. Never blocks.

        ``buttons`` is up to three ``(label, variant, callback)`` tuples;
        variant is a :func:`videokidnapper.ui.theme.button` style
        ("primary", "secondary" or "ghost"). A click closes the prompt and
        then calls ``callback`` (None for a button that only closes). A
        fourth item, False, keeps the prompt open after the click, for
        "Retry" or "Release notes" style buttons.

        ``dismiss`` adds a ✕: a callable runs when it is clicked, True
        just closes. None means no ✕, so one of the buttons must be used.

        ``key`` names the question: asking again with the key of an open
        prompt replaces it in its place in the queue, so the same
        question never stacks up. ``urgent`` is for prompts that answer
        something the user just did, such as closing the window: it is
        shown straight away and whatever was showing comes back after.

        A prompt asked from inside another prompt's callback is its
        follow-up and is shown next, ahead of older prompts.
        """
        prompt = Prompt(self, message, buttons, detail, dismiss, tone, progress, key)
        slot = self._vacate(key)
        if urgent:
            self._show_now(prompt)
        elif slot == "current":
            self.current = prompt
            self._notify()
        elif slot is not None:
            self.pending.insert(slot, prompt)
        elif self._followups is not None:
            self.pending.insert(self._followups, prompt)
            self._followups += 1
        else:
            self.pending.append(prompt)
            if self.current is None:
                self._show_next()
        return prompt

    def progress(self, message, value=0.0, **kwargs):
        """``ask`` with a determinate progress bar, starting at ``value``."""
        return self.ask(message, progress=0.0 if value is None else value, **kwargs)

    # -- internals ---------------------------------------------------------
    def _vacate(self, key):
        """Remove the open prompt named ``key``; return where it was."""
        if key is None:
            return None
        if self.current is not None and self.current.key == key:
            self.current = None
            return "current"
        for index, prompt in enumerate(self.pending):
            if prompt.key == key:
                del self.pending[index]
                return index
        return None

    def _show_now(self, prompt):
        if self.current is not None:
            self.pending.insert(0, self.current)
        self.current = prompt
        self._notify()

    def _show_next(self):
        self.current = self.pending.pop(0) if self.pending else None
        self._notify()

    def _notify(self, full=True):
        if self._on_change is not None:
            self._on_change(self.current, full)

    def _detach(self, prompt):
        """Take ``prompt`` out of the queue without showing the next one.

        Returns False when it was not open.
        """
        if self.current is prompt:
            self.current = None
            return True
        if prompt in self.pending:
            self.pending.remove(prompt)
            return True
        return False

    def _close(self, prompt):
        if self._detach(prompt) and self.current is None and self._followups is None:
            self._show_next()

    def _answer(self, prompt, command, closes, answer):
        if not prompt.is_open:
            # A second click, or a click on a prompt that was replaced.
            return False
        if not closes:
            if command is not None:
                command()
            return True
        prompt.answer = answer
        self._detach(prompt)
        outer = self._followups
        self._followups = 0
        try:
            if command is not None:
                command()
        finally:
            self._followups = outer
            if self.current is None and outer is None:
                self._show_next()
        return True

    def _changed(self, prompt, full):
        if prompt is self.current:
            self._notify(full)


_TONE_STYLE = {
    # tone: (background, accent, bottom edge, icon)
    "info":    (T.ACCENT_SOFT, T.ACCENT, T.BORDER, "info"),
    "warn":    (T.WARN_SOFT, T.WARN, T.WARN_EDGE, "warning"),
    "success": (T.BG_SURFACE, T.SUCCESS, T.BORDER, "check"),
}


class InlineBanner(ctk.CTkFrame):
    """The bar that shows a :class:`PromptQueue`.

    ``master`` is the window and ``anchor`` the widget whose top edge the
    bar covers (the workspace host). The bar is placed over the anchor
    rather than packed above it, so it takes no layout space and the
    workspaces never jump when it comes and goes. It is 41 px tall, the
    height of the panel headers it sits over.
    """

    HEIGHT = 41

    def __init__(self, master, anchor, **kwargs):
        super().__init__(master, height=self.HEIGHT, corner_radius=0,
                         fg_color=T.ACCENT_SOFT, **kwargs)
        self.pack_propagate(False)
        self._anchor = anchor
        self._shown = None
        self._button_widgets = []

        self._stripe = ctk.CTkFrame(self, width=4, corner_radius=0, fg_color=T.ACCENT)
        self._stripe.pack(side="left", fill="y")
        self._icon = ctk.CTkLabel(self, text="", width=22, font=icon_font(14),
                                  text_color=T.ACCENT)
        self._icon.pack(side="left", padx=(12, 6))
        self._close_btn = icon_button(self, "close", size=28, icon_size=10,
                                      command=self._dismiss_clicked)
        self._close_btn.pack(side="right", padx=(2, 8))
        self._actions = ctk.CTkFrame(self, fg_color="transparent")
        self._actions.pack(side="right", padx=(8, 2))
        self._progress = ctk.CTkProgressBar(
            self, width=180, height=6, corner_radius=3,
            progress_color=T.ACCENT, fg_color=T.BG_ACTIVE,
        )
        self._message = ctk.CTkLabel(self, text="", font=T.font(T.SIZE_MD, "bold"),
                                     text_color=T.TEXT, anchor="w")
        self._message.pack(side="left")
        # Packed last, so on a narrow window the detail is what gets cut.
        self._detail = ctk.CTkLabel(self, text="", font=T.font(T.SIZE_SM),
                                    text_color=T.TEXT_MUTED, anchor="w")
        self._detail.pack(side="left", fill="x", expand=True, padx=(10, 0))
        self._edge = ctk.CTkFrame(self, height=1, corner_radius=0, fg_color=T.BORDER)
        self._edge.place(x=0, rely=1.0, relwidth=1.0, anchor="sw")

        self.prompts = PromptQueue(on_change=self._render)

    # -- the queue's API, so callers write app.banner.ask(...) --------------
    def ask(self, *args, **kwargs):
        return self.prompts.ask(*args, **kwargs)

    def progress(self, *args, **kwargs):
        return self.prompts.progress(*args, **kwargs)

    @property
    def current(self):
        return self.prompts.current

    @property
    def pending(self):
        return list(self.prompts.pending)

    # -- drawing -----------------------------------------------------------
    def _render(self, prompt, full=True):
        try:
            self._show(prompt, full)
        except tk.TclError:
            # The answer ended the app ("Don't save" closes the window), so
            # there is nothing left to draw the next prompt in.
            pass

    def _show(self, prompt, full):
        if prompt is None:
            self._shown = None
            self.place_forget()
            return
        if full or prompt is not self._shown:
            self._paint(prompt)
        else:
            self._paint_text(prompt)
        self._shown = prompt
        self.place(in_=self._anchor, x=0, y=0, relwidth=1.0)
        self.lift()

    def _paint(self, prompt):
        background, accent, edge, icon = _TONE_STYLE[prompt.tone]
        self.configure(fg_color=background)
        self._actions.configure(fg_color=background)
        self._stripe.configure(fg_color=accent)
        self._edge.configure(fg_color=edge)
        self._icon.configure(text=glyph(icon), text_color=accent)
        self._progress.configure(progress_color=accent)

        for widget in self._button_widgets:
            # Destroyed a moment later, not now: a CTkButton redraws itself
            # 100 ms after a click, and that click is often what brought
            # the next prompt here. Destroying it now raised a TclError.
            widget.pack_forget()
            self.after(300, widget.destroy)
        self._button_widgets = []
        for item in prompt.buttons:
            widget = button(
                self._actions, item.label, variant=item.variant, height=28,
                width=0, font=T.font(T.SIZE_SM, "bold"),
                command=lambda p=prompt, label=item.label: self._button_clicked(p, label),
            )
            widget.pack(side="left", padx=(6, 0))
            self._button_widgets.append(widget)

        if prompt.dismissable:
            self._close_btn.pack(side="right", padx=(2, 8), before=self._actions)
        else:
            self._close_btn.pack_forget()
        self._paint_text(prompt)

    def _paint_text(self, prompt):
        self._message.configure(text=prompt.message)
        self._detail.configure(text=prompt.detail or "")
        if prompt.progress is None:
            self._progress.pack_forget()
        else:
            self._progress.set(prompt.progress)
            if not self._progress.winfo_manager():
                self._progress.pack(side="right", padx=(12, 4), before=self._message)

    # -- clicks ------------------------------------------------------------
    def _button_clicked(self, prompt, label):
        prompt.press(label)

    def _dismiss_clicked(self):
        if self._shown is not None:
            self._shown.dismiss()
