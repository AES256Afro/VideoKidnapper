# SPDX-FileCopyrightText: 2026 AES256Afro <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""The inline banner that replaced every yes/no popup.

Most of it is the queue's rules, which run without a display. The last
few tests draw the real bar on a withdrawn window and skip when there is
no display, like the rest of the UI tests.
"""

import pytest

ctk = pytest.importorskip("customtkinter", reason="needs customtkinter")

from videokidnapper.ui.studio.banner import MAX_BUTTONS, PromptQueue  # noqa: E402


def _queue():
    seen = []
    queue = PromptQueue(on_change=lambda prompt, full: seen.append((prompt, full)))
    return queue, seen


# -- one at a time, in order ----------------------------------------------------

def test_prompts_queue_and_show_one_at_a_time():
    queue, seen = _queue()
    first = queue.ask("First?", buttons=[("OK", "primary", None)])
    second = queue.ask("Second?", buttons=[("OK", "primary", None)])

    assert queue.current is first
    assert queue.pending == [second]
    assert first.showing and not second.showing
    assert second.is_open

    first.press("OK")
    assert queue.current is second
    assert not first.is_open
    second.press("OK")
    assert queue.current is None
    assert seen[-1] == (None, True), "the bar hides when the queue is empty"


def test_a_button_closes_the_prompt_and_then_runs_its_callback():
    queue, _ = _queue()
    calls = []
    prompt = queue.ask("Save?", buttons=[
        ("Save", "primary", lambda: calls.append(("save", prompt.is_open))),
        ("Cancel", "ghost", lambda: calls.append("cancel")),
    ])
    assert prompt.press("Save") is True
    assert calls == [("save", False)]
    assert prompt.answer == "Save"
    # Answered once: a second click (or a stale one) does nothing.
    assert prompt.press("Cancel") is False
    assert calls == [("save", False)]


def test_a_keep_open_button_leaves_the_prompt_up():
    queue, _ = _queue()
    calls = []
    prompt = queue.ask("Update ready", buttons=[
        ("Release notes", "ghost", lambda: calls.append("notes"), False),
    ])
    prompt.press("Release notes")
    assert calls == ["notes"]
    assert prompt.showing
    assert prompt.answer is None


def test_unknown_button_is_not_an_answer():
    queue, _ = _queue()
    prompt = queue.ask("Q", buttons=[("Yes", "primary", None)])
    assert prompt.press("No") is False
    assert prompt.showing


def test_at_most_three_buttons():
    queue, _ = _queue()
    buttons = [(str(i), "ghost", None) for i in range(MAX_BUTTONS + 1)]
    with pytest.raises(ValueError):
        queue.ask("Too many", buttons=buttons)


# -- the ✕ -----------------------------------------------------------------------

def test_dismiss_runs_its_own_callback():
    queue, _ = _queue()
    calls = []
    prompt = queue.ask("Recover?", buttons=[("Recover", "primary", lambda: calls.append("r"))],
                       dismiss=lambda: calls.append("later"))
    assert prompt.dismissable
    assert prompt.dismiss() is True
    assert calls == ["later"]
    assert prompt.answer == "dismiss"
    assert queue.current is None


def test_without_dismiss_there_is_no_x():
    queue, _ = _queue()
    prompt = queue.ask("Pick one", buttons=[("A", "primary", None)])
    assert not prompt.dismissable
    assert prompt.dismiss() is False
    assert prompt.showing


def test_dismiss_true_only_closes():
    queue, _ = _queue()
    prompt = queue.ask("Note", dismiss=True)
    assert prompt.dismiss() is True
    assert not prompt.is_open


# -- closing, replacing, jumping the queue ------------------------------------------

def test_close_takes_a_prompt_away_without_any_callback():
    queue, _ = _queue()
    calls = []
    first = queue.ask("A", buttons=[("OK", "primary", lambda: calls.append("a"))],
                      dismiss=lambda: calls.append("a-x"))
    second = queue.ask("B", buttons=[("OK", "primary", lambda: calls.append("b"))])
    third = queue.ask("C")

    second.close()                       # waiting: just leaves the queue
    assert queue.pending == [third]
    first.close()                        # showing: the next one appears
    assert queue.current is third
    assert calls == []
    first.close()                        # closing twice is harmless
    assert queue.current is third


def test_the_same_key_replaces_a_prompt_in_its_place():
    queue, _ = _queue()
    old = queue.ask("Theme set to Retro.", key="theme")
    waiting = queue.ask("Other")
    new = queue.ask("Theme set to Fallout.", key="theme")
    assert queue.current is new
    assert queue.pending == [waiting]
    assert not old.is_open

    queued = queue.ask("Queued", key="q")
    replacement = queue.ask("Queued again", key="q")
    assert queue.pending == [waiting, replacement]
    assert not queued.is_open


def test_urgent_prompts_show_now_and_the_displaced_one_comes_back():
    queue, _ = _queue()
    theme = queue.ask("Restart for the theme?")
    later = queue.ask("Later one")
    close = queue.ask("Save before closing?", urgent=True)
    assert queue.current is close
    assert queue.pending == [theme, later]
    close.close()
    assert queue.current is theme


def test_a_follow_up_comes_before_older_prompts():
    queue, _ = _queue()
    asked = {}

    def stop_and_close():
        asked["save"] = queue.ask("Save your project?")
        asked["then"] = queue.ask("And then?")

    queue.ask("An export is running.", buttons=[("Stop", "primary", stop_and_close)])
    older = queue.ask("Recover unsaved work?")
    queue.current.press("Stop")
    assert queue.current is asked["save"]
    assert queue.pending == [asked["then"], older]


# -- progress ------------------------------------------------------------------------

def test_progress_prompts_move_without_a_full_redraw():
    queue, seen = _queue()
    prompt = queue.progress("Downloading v2.0", detail="0 of 30 MB")
    assert prompt.progress == 0.0
    seen.clear()
    prompt.set_progress(0.5, detail="15 of 30 MB")
    assert prompt.progress == 0.5 and prompt.detail == "15 of 30 MB"
    assert seen == [(prompt, False)]

    prompt.set_progress(7)
    assert prompt.progress == 1.0
    prompt.set_progress(float("nan"))
    assert prompt.progress == 0.0

    # Turning the download into "restart to update" is one update call.
    seen.clear()
    prompt.update(message="v2.0 is ready", progress=None, tone="success",
                  buttons=[("Restart to update", "primary", None)])
    assert prompt.progress is None and prompt.tone == "success"
    assert seen == [(prompt, True)]


def test_updating_a_waiting_prompt_does_not_redraw():
    queue, seen = _queue()
    queue.ask("Showing")
    waiting = queue.progress("Waiting")
    seen.clear()
    waiting.set_progress(0.3)
    assert seen == []


def test_unknown_tone_falls_back_to_info():
    queue, _ = _queue()
    assert queue.ask("x", tone="shouting").tone == "info"


# -- the drawn bar ---------------------------------------------------------------------

@pytest.fixture(scope="module")
def root():
    try:
        instance = ctk.CTk()
    except Exception as exc:  # pragma: no cover - headless CI
        pytest.skip(f"no usable display: {type(exc).__name__}: {exc}")
    instance.withdraw()
    yield instance
    try:
        instance.destroy()
    except Exception:
        pass


@pytest.fixture
def banner(root):
    from videokidnapper.ui.studio.banner import InlineBanner

    host = ctk.CTkFrame(root)
    host.pack(fill="both", expand=True)
    bar = InlineBanner(root, anchor=host)
    yield bar
    bar.destroy()
    host.destroy()


def _texts(widgets):
    return [widget.cget("text") for widget in widgets]


def test_the_bar_floats_over_its_anchor_only_while_asking(banner):
    assert banner.winfo_manager() == ""
    calls = []
    banner.ask("Theme set to Retro. Restart to apply it.",
               buttons=[("Restart now", "primary", lambda: calls.append("restart")),
                        ("Later", "ghost", lambda: calls.append("later"))],
               dismiss=lambda: calls.append("x"))
    # Placed, not packed: it takes no room from the workspaces.
    assert banner.winfo_manager() == "place"
    assert str(banner.place_info()["in"]) == str(banner._anchor)
    assert banner._message.cget("text") == "Theme set to Retro. Restart to apply it."
    assert _texts(banner._button_widgets) == ["Restart now", "Later"]
    assert banner._close_btn.winfo_manager() == "pack"

    banner._button_widgets[1].invoke()
    assert calls == ["later"]
    assert banner.winfo_manager() == ""


def test_the_x_button_dismisses_and_the_next_prompt_appears(banner):
    calls = []
    banner.ask("Recover unsaved work?", buttons=[("Recover", "primary", None)],
               dismiss=lambda: calls.append("later"))
    banner.ask("Second", buttons=[("OK", "primary", None)])
    banner._close_btn.invoke()
    assert calls == ["later"]
    assert banner._message.cget("text") == "Second"
    assert _texts(banner._button_widgets) == ["OK"]
    # No dismiss given: no ✕.
    assert banner._close_btn.winfo_manager() == ""
    banner._button_widgets[0].invoke()
    assert banner.winfo_manager() == ""


def test_the_progress_bar_shows_only_for_progress_prompts(banner):
    prompt = banner.progress("Downloading", value=0.25, detail="7 of 28 MB")
    assert banner._progress.winfo_manager() == "pack"
    assert banner._progress.get() == pytest.approx(0.25)
    prompt.set_progress(0.75, detail="21 of 28 MB")
    assert banner._progress.get() == pytest.approx(0.75)
    assert banner._detail.cget("text") == "21 of 28 MB"
    prompt.update(progress=None, message="Ready")
    assert banner._progress.winfo_manager() == ""
    prompt.close()
    assert banner.winfo_manager() == ""
