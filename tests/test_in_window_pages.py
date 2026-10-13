# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Setup and the keyboard shortcuts are pages inside the window.

Both used to open windows of their own. The rule now is one window: a
page takes over the workspace area, and Back (or Esc) returns to the
workspace the user came from. These tests pin:

- the pages build, lazily, and their buttons reach the right helpers
  (installers, the admin terminal and relaunch are all stubbed: nothing
  here downloads, installs or opens a terminal);
- ``?`` toggles the shortcuts page. The old window closed itself on
  ``?`` and the app-wide binding then opened it again;
- ``?`` typed into a text field is just a question mark;
- the first-run landing shows Setup in its own place, not in a window;
- plugin workspaces still work alongside the pages.

The App itself is not built: a stand-in carries the real App methods
on a withdrawn root, so no window ever appears. Skips without a display,
like the rest of the UI tests.
"""

import threading
import time
import tkinter as tk
from tkinter import ttk
from types import SimpleNamespace

import pytest

ctk = pytest.importorskip("customtkinter", reason="needs customtkinter")

from videokidnapper import app as app_module  # noqa: E402
from videokidnapper.ui import setup_page  # noqa: E402
from videokidnapper.ui.setup_page import SetupPage  # noqa: E402
from videokidnapper.ui.shortcuts_page import ShortcutsPage, split_columns  # noqa: E402
from videokidnapper.ui.studio.chrome import WorkspaceHost  # noqa: E402
from videokidnapper.utils import prereq_check  # noqa: E402

App = app_module.App
TAB_SETUP = app_module.TAB_SETUP
TAB_SHORTCUTS = app_module.TAB_SHORTCUTS


@pytest.fixture(scope="module")
def root():
    """One withdrawn root for the module: it is never shown."""
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


def _status(missing=()):
    """A check_all() result with ``missing`` (display names) not installed."""
    names = ["FFmpeg", "customtkinter", "Pillow", "yt-dlp", "mss", "tkinterdnd2"]
    result = {}
    for name in names:
        installed = name not in missing
        result[name] = {"installed": installed, "version": "1.0" if installed else None}
    result["FFmpeg"]["path"] = "C:/ffmpeg.exe" if "FFmpeg" not in missing else None
    return result


@pytest.fixture(autouse=True)
def no_real_side_effects(monkeypatch):
    """Nothing here may download, install, open a terminal or relaunch."""
    calls = SimpleNamespace(check_all=0, missing=["FFmpeg", "tkinterdnd2"],
                            terminal=[], relaunch=0)

    def check_all():
        calls.check_all += 1
        return _status(calls.missing)

    def forbidden(*_a, **_k):
        raise AssertionError("a real installer or process was started")

    def open_admin_terminal(commands):
        calls.terminal.append(list(commands))
        return True, "Launched elevated PowerShell."

    def relaunch():
        calls.relaunch += 1

    monkeypatch.setattr(prereq_check, "check_all", check_all)
    monkeypatch.setattr(prereq_check, "install_ffmpeg_portable", forbidden)
    monkeypatch.setattr(prereq_check, "pip_install_streaming", forbidden)
    monkeypatch.setattr(prereq_check.subprocess, "Popen", forbidden)
    monkeypatch.setattr(prereq_check, "open_admin_terminal", open_admin_terminal)
    monkeypatch.setattr(prereq_check, "relaunch", relaunch)
    return calls


def _toplevels(widget):
    """Every Toplevel under ``widget``: a page must never open one."""
    found = []
    for child in widget.winfo_children():
        if isinstance(child, tk.Toplevel):
            found.append(child)
        found.extend(_toplevels(child))
    return found


# ---------------------------------------------------------------------------
# A stand-in App: the real methods, a real WorkspaceHost, no real window.

_APP_METHODS = (
    "show_workspace", "_on_tab_changed", "_ensure_tab", "_tab_if_built",
    "_construct_setup_page", "_construct_shortcuts_page",
    "_open_page", "_close_page", "_return_target", "_workspace_title",
    "_open_setup_page", "_toggle_shortcuts_page",
    "_shortcut_shortcuts_overlay", "_escape_shortcut", "_editing_in_entry",
    "_bind_keyboard_shortcuts", "_bind_accel", "_shortcut", "_paste_shortcut",
    "_save_project_shortcut", "_save_project_as_shortcut",
    "_open_project_shortcut", "register_tab",
)


class StandInApp:
    def __init__(self, root):
        self.host_frame = ctk.CTkFrame(root)
        self.workspaces = WorkspaceHost(self.host_frame)
        for key in ("import", "edit", "export", "log"):
            self.workspaces.add(key)
        self.workspaces.set("edit")
        self._built_tabs = {}
        self._lazy_tabs = {
            TAB_SETUP: self._construct_setup_page,
            TAB_SHORTCUTS: self._construct_shortcuts_page,
        }
        self.logged = []
        self.debug_tab = SimpleNamespace(add_log=lambda text, level: self.logged.append(level))
        self.switcher = SimpleNamespace(items=[])
        self.switcher.add_item = lambda key, label: self.switcher.items.append(key)
        self.restarts = 0
        self.bindings = {}
        self.binding_adds = {}
        self._bind_keyboard_shortcuts()

    def bind_all(self, sequence, handler, add=None):
        self.bindings[sequence] = handler
        self.binding_adds[sequence] = add

    def _restart_app(self):
        self.restarts += 1

    def press(self, sequence, widget=None):
        return self.bindings[sequence](SimpleNamespace(widget=widget or self.host_frame))

    def destroy(self):
        self.host_frame.destroy()


for _name in _APP_METHODS:
    setattr(StandInApp, _name, vars(App)[_name])


@pytest.fixture
def app(root):
    instance = StandInApp(root)
    yield instance
    instance.destroy()


# ---------------------------------------------------------------------------
# Setup page

@pytest.fixture
def page(root):
    events = SimpleNamespace(back=0, relaunch=0)
    widget = SetupPage(root, on_back=lambda: setattr(events, "back", events.back + 1),
                       on_relaunch=lambda: setattr(events, "relaunch", events.relaunch + 1))
    widget.events = events
    yield widget
    widget.destroy()


def test_setup_page_ticks_what_is_missing(page):
    assert page._selected["ffmpeg"].get() and page._selected["tkinterdnd2"].get()
    assert not page._selected["mss"].get()
    assert str(page._rows["mss"]["checkbox"].cget("state")) == "disabled"
    assert page._select_all_var.get()
    assert str(page.install_btn.cget("state")) == "normal"
    assert "FFmpeg" in page.plan_label.cget("text")
    assert str(page.relaunch_btn.cget("state")) == "disabled"


def test_select_all_missing_toggles_only_the_missing_rows(page):
    page._select_all_var.set(False)
    page._toggle_select_all()
    assert not page._selected["ffmpeg"].get()
    assert not page._selected["tkinterdnd2"].get()
    assert str(page.install_btn.cget("state")) == "disabled"

    page._select_all_var.set(True)
    page._toggle_select_all()
    assert page._selected["ffmpeg"].get() and page._selected["tkinterdnd2"].get()
    assert not page._selected["mss"].get(), "an installed row was ticked"


def test_install_runs_in_the_background_and_lights_relaunch(page, monkeypatch,
                                                           no_real_side_effects):
    runs = []

    def fake_runner(widget, keys, on_line=None, on_progress=None, on_done=None, **_kw):
        runs.append(SimpleNamespace(widget=widget, keys=keys, on_line=on_line,
                                    on_progress=on_progress, on_done=on_done))

    monkeypatch.setattr(setup_page, "install_in_background", fake_runner)
    page._selected["tkinterdnd2"].set(False)
    page._install_selected()

    assert [run.keys for run in runs] == [["ffmpeg"]], "only the ticked, missing rows"
    run = runs[0]
    assert run.widget is page
    assert page.installing
    assert str(page.install_btn.cget("state")) == "disabled"
    page._install_selected()
    assert len(runs) == 1, "a second click started a second install"

    # Refreshing mid-install would re-tick rows under the running install.
    checks = no_real_side_effects.check_all
    page.refresh()
    assert no_real_side_effects.check_all == checks

    run.on_line("Downloading FFmpeg... 10%")
    run.on_line("Downloading FFmpeg... 10%")
    run.on_progress(0.5, "Downloading FFmpeg... 50%")
    assert float(page.progress.get()) == pytest.approx(0.5)
    assert page.status_label.cget("text") == "Downloading FFmpeg... 50%"

    no_real_side_effects.missing = ["tkinterdnd2"]
    run.on_done(["ffmpeg"], [])
    console = page.console.get("1.0", "end")
    assert console.count("Downloading FFmpeg... 10%") == 1, "repeats were echoed"
    assert "Done. Installed: ffmpeg" in console
    assert not page.installing
    assert str(page.relaunch_btn.cget("state")) == "normal"
    assert page._rows["ffmpeg"]["icon"].cget("text") == "✓"

    page.relaunch_btn.invoke()
    assert page.events.relaunch == 1


def test_a_failed_install_says_why(page, monkeypatch):
    captured = {}
    monkeypatch.setattr(setup_page, "install_in_background",
                        lambda widget, keys, **kw: captured.update(kw))
    page._install_selected()
    captured["on_done"]([], [("ffmpeg", "SHA-256 mismatch")])
    assert "Failed: ffmpeg" in page.status_label.cget("text")
    assert "SHA-256 mismatch" in page.status_label.cget("text")
    assert str(page.relaunch_btn.cget("state")) == "disabled"
    assert not page.installing


def test_admin_terminal_shows_and_runs_the_commands(page, no_real_side_effects):
    page.terminal_btn.invoke()
    assert len(no_real_side_effects.terminal) == 1
    commands = no_real_side_effects.terminal[0]
    assert commands
    console = page.console.get("1.0", "end")
    assert "Admin terminal will run" in console
    assert all(command in console for command in commands)
    assert "Refresh" in page.status_label.cget("text")


def test_admin_terminal_failure_copies_the_commands(page, monkeypatch):
    tried = []

    def no_terminal(commands):
        tried.append(commands)
        return False, "No supported terminal emulator found."

    monkeypatch.setattr(prereq_check, "open_admin_terminal", no_terminal)
    clipboard = []
    # Stubbed: the real clipboard belongs to the user.
    monkeypatch.setattr(page, "clipboard_clear", clipboard.clear)
    monkeypatch.setattr(page, "clipboard_append", clipboard.append)
    page._open_admin_terminal()
    assert clipboard == ["\n".join(tried[0])]
    assert "No supported terminal" in page.status_label.cget("text")


def test_relaunch_without_the_app_restarts_the_process(root, no_real_side_effects):
    widget = SetupPage(root, on_back=lambda: None)
    try:
        widget._relaunch()
    finally:
        widget.destroy()
    assert no_real_side_effects.relaunch == 1


def test_back_button_calls_back(page):
    page.back_button.invoke()
    assert page.events.back == 1


def test_install_in_background_reports_on_the_tk_thread(root, monkeypatch):
    def fake_install(keys, line_cb=None, progress_cb=None):
        line_cb("$ pip install --user mss")
        progress_cb(0.5, "Installing mss…")
        return ["mss"], [("yt_dlp", "offline")]

    monkeypatch.setattr(prereq_check, "install_missing", fake_install)
    seen, done = [], []
    main = threading.main_thread()

    def record(kind):
        def callback(*args):
            assert threading.current_thread() is main, "Tk touched off the main thread"
            (done if kind == "done" else seen).append((kind, *args))
        return callback

    setup_page.install_in_background(
        root, ["mss", "yt_dlp"], on_line=record("line"),
        on_progress=record("progress"), on_done=record("done"), poll_ms=10,
    )
    _pump_until(root, lambda: done)
    assert seen == [("line", "$ pip install --user mss"),
                    ("progress", 0.5, "Installing mss…")]
    assert done == [("done", ["mss"], [("yt_dlp", "offline")])]


def test_install_in_background_never_strands_the_page(root, monkeypatch):
    def broken(keys, line_cb=None, progress_cb=None):
        raise RuntimeError("disk full")

    monkeypatch.setattr(prereq_check, "install_missing", broken)
    done = []
    setup_page.install_in_background(root, ["ffmpeg"], on_done=lambda *a: done.append(a),
                                     poll_ms=10)
    _pump_until(root, lambda: done)
    installed, failures = done[0]
    assert installed == [] and failures[0][0] == "ffmpeg"
    assert "disk full" in failures[0][1]


def _pump_until(root, condition, timeout=5.0):
    # The root is withdrawn before it ever maps, so update() keeps it hidden.
    deadline = time.monotonic() + timeout
    while not condition() and time.monotonic() < deadline:
        root.update()
        time.sleep(0.01)
    assert condition(), "the background install never reported back"


# ---------------------------------------------------------------------------
# Shortcuts page

def test_shortcuts_page_builds_and_back_works(root):
    backs = []
    widget = ShortcutsPage(root, on_back=lambda: backs.append(1))
    try:
        widget.back_button.invoke()
    finally:
        widget.destroy()
    assert backs == [1]


def test_shortcut_groups_split_into_balanced_columns_in_order():
    groups = [("A", [1, 2, 3]), ("B", [1, 2]), ("C", [1, 2]), ("D", [1, 2, 3, 4])]
    left, right = split_columns(groups)
    assert [g for g, _ in left] + [g for g, _ in right] == ["A", "B", "C", "D"]
    assert [g for g, _ in left] == ["A", "B"]
    assert split_columns([("A", [1])]) == [[("A", [1])], []]


def test_pages_never_open_a_window_of_their_own():
    from pathlib import Path

    ui = Path(setup_page.__file__).resolve().parent
    for name in ("setup_page.py", "shortcuts_page.py"):
        source = (ui / name).read_text(encoding="utf-8")
        assert "Toplevel" not in source, f"{name} opens a window"
        assert "messagebox" not in source, f"{name} opens a message box"


# ---------------------------------------------------------------------------
# The app's side: building, Back, `?` and Esc

def test_pages_are_built_on_first_view_and_reused(app, root):
    assert app._built_tabs == {}
    app._open_page(TAB_SHORTCUTS)
    assert app.workspaces.get() == TAB_SHORTCUTS
    first = app._tab_if_built(TAB_SHORTCUTS)
    assert isinstance(first, ShortcutsPage)
    app._close_page()
    app._open_page(TAB_SHORTCUTS)
    assert app._tab_if_built(TAB_SHORTCUTS) is first, "the page was rebuilt"

    app._open_setup_page()
    assert app.workspaces.get() == TAB_SETUP
    assert isinstance(app._tab_if_built(TAB_SETUP), SetupPage)
    assert _toplevels(root) == []


def test_back_returns_to_the_workspace_the_user_came_from(app):
    app.workspaces.set("import")
    app._open_page(TAB_SETUP)
    page = app._tab_if_built(TAB_SETUP)
    assert page.back_button.cget("text") == "‹  Back to Import"
    page.back_button.invoke()
    assert app.workspaces.get() == "import"

    app.workspaces.set("export")
    app._open_page(TAB_SHORTCUTS)
    # Hopping from one page to the other keeps the original way back.
    app._open_page(TAB_SETUP)
    assert page.back_button.cget("text") == "‹  Back to Export"
    app._close_page()
    assert app.workspaces.get() == "export"

    app.workspaces.set("log")
    app._open_page(TAB_SETUP)
    assert page.back_button.cget("text") == "‹  Back to Debug log"
    app._close_page()
    assert app.workspaces.get() == "log"


def test_setup_looks_again_each_time_it_is_shown(app, no_real_side_effects):
    app._open_page(TAB_SETUP)
    assert no_real_side_effects.check_all == 1
    app._close_page()
    no_real_side_effects.missing = []
    app._open_page(TAB_SETUP)
    assert no_real_side_effects.check_all == 2
    page = app._tab_if_built(TAB_SETUP)
    assert "Everything is installed" in page.plan_label.cget("text")


def test_setup_relaunch_goes_through_the_app(app):
    app._open_page(TAB_SETUP)
    app._tab_if_built(TAB_SETUP)._relaunch()
    assert app.restarts == 1, "relaunch skipped App._restart_app and its save prompts"


def test_question_mark_toggles_the_shortcuts_page(app):
    assert app.press("<Key-question>") == "break"
    assert app.workspaces.get() == TAB_SHORTCUTS
    # The old window closed itself on `?` and was then reopened by this
    # same binding. Now the second press simply goes back.
    app.press("<Key-question>")
    assert app.workspaces.get() == "edit"

    app.workspaces.set("import")
    app.press("<Key-question>")
    app.press("<Key-question>")
    assert app.workspaces.get() == "import"


def test_the_header_help_button_toggles_too(app):
    app._toggle_shortcuts_page()
    assert app.workspaces.get() == TAB_SHORTCUTS
    app._toggle_shortcuts_page()
    assert app.workspaces.get() == "edit"


def test_question_mark_in_a_text_field_is_just_typed(app, root):
    entry = ctk.CTkEntry(root)
    textbox = ctk.CTkTextbox(root)
    combo = ctk.CTkComboBox(root, values=["a"])
    plain = [tk.Entry(root), tk.Text(root), ttk.Entry(root), ttk.Combobox(root)]
    try:
        for widget in (entry._entry, textbox._textbox, combo._entry, *plain):
            assert app.press("<Key-question>", widget) is None, widget.winfo_class()
            assert app.workspaces.get() == "edit", f"? in a {widget.winfo_class()} opened the page"
    finally:
        for widget in (entry, textbox, combo, *plain):
            widget.destroy()


def test_escape_leaves_a_page_and_is_left_alone_elsewhere(app):
    assert app.binding_adds["<Escape>"] == "+", "Esc must not replace other Esc bindings"
    assert app.press("<Escape>") is None
    assert app.workspaces.get() == "edit"

    app.workspaces.set("export")
    app._open_page(TAB_SHORTCUTS)
    assert app.press("<Escape>") == "break"
    assert app.workspaces.get() == "export"

    app._open_page(TAB_SETUP)
    app.press("<Escape>")
    assert app.workspaces.get() == "export"


def test_a_page_that_fails_to_build_leaves_the_window_alone(app, monkeypatch):
    def boom():
        raise RuntimeError("simulated failure")

    monkeypatch.setitem(app._lazy_tabs, TAB_SETUP, boom)
    app._open_page(TAB_SETUP)
    assert app.workspaces.get() == "edit"
    assert app.logged == ["ERROR"]


def test_plugin_workspaces_work_alongside_the_pages(app):
    built = []

    def factory(parent):
        widget = ctk.CTkFrame(parent)
        built.append(widget)
        return widget

    assert app.register_tab("Hello", factory) is built[0]
    # A plugin called "setup" gets its own workspace, not the Setup page.
    assert app.register_tab("setup", factory) is built[1]
    assert app.switcher.items == ["plugin:Hello", "plugin:setup"]

    app.show_workspace("plugin:Hello")
    app._open_page(TAB_SETUP)
    page = app._tab_if_built(TAB_SETUP)
    assert isinstance(page, SetupPage)
    assert page.back_button.cget("text") == "‹  Back to Hello"
    app.press("<Escape>")
    assert app.workspaces.get() == "plugin:Hello"
    assert built[1].winfo_exists() and built[1].master is app.workspaces.tab("plugin:setup")


# ---------------------------------------------------------------------------
# The first-run landing

class LandingStandIn(ctk.CTkFrame):
    """The App while it shows the first-run landing: no workspaces yet."""

    def __init__(self, master):
        super().__init__(master)
        self._setup_frame = ctk.CTkFrame(self)
        self._setup_frame.place(relx=0.5, rely=0.5, anchor="center")
        self.rechecks = 0
        self.restarts = 0
        self.progress = []
        self.messages = []
        self.finished = []
        self._setup_progress = SimpleNamespace(set=self.progress.append)
        self._setup_msg = SimpleNamespace(
            configure=lambda text=None, **_k: self.messages.append(text))

    def _recheck_setup(self):
        self.rechecks += 1

    def _restart_app(self):
        self.restarts += 1

    def _on_auto_install_done(self, installed, failures):
        self.finished.append((installed, failures))

    def _finish_setup_and_launch(self):
        self.finished.append("launched")


for _name in ("_open_setup_page", "_show_setup_over_landing",
              "_close_setup_over_landing", "_auto_install_prereqs"):
    setattr(LandingStandIn, _name, vars(App)[_name])


@pytest.fixture
def landing(root):
    widget = LandingStandIn(root)
    widget.pack(fill="both", expand=True)
    yield widget
    widget.destroy()


def test_landing_review_details_shows_setup_in_place(landing, root):
    landing._open_setup_page()
    page = landing._landing_setup_page
    assert isinstance(page, SetupPage)
    assert page.master is landing
    assert not landing._setup_frame.place_info(), "the landing is still showing"
    assert _toplevels(root) == []

    landing._open_setup_page()
    assert landing._landing_setup_page is page, "a second Setup page was stacked"

    page._relaunch()
    assert landing.restarts == 1

    page.back_button.invoke()
    assert not page.winfo_exists()
    assert landing._landing_setup_page is None
    assert landing.rechecks == 1, "Back must look again at what is installed"


def test_landing_back_waits_for_a_running_install(landing, monkeypatch):
    monkeypatch.setattr(setup_page, "install_in_background", lambda *a, **k: None)
    landing._open_setup_page()
    page = landing._landing_setup_page
    page._install_selected()
    page.back_button.invoke()
    assert page.winfo_exists() and landing.rechecks == 0
    assert "Still installing" in page.status_label.cget("text")


def test_landing_install_uses_the_shared_runner(landing, monkeypatch):
    runs = []
    monkeypatch.setattr(setup_page, "install_in_background",
                        lambda widget, keys, **kw: runs.append((widget, keys, kw)))
    landing._auto_install_prereqs(["ffmpeg"])
    (widget, keys, kw), = runs
    assert widget is landing and keys == ["ffmpeg"]
    kw["on_progress"](0.25, "Downloading FFmpeg... 25%")
    assert landing.progress == [0.25]
    assert landing.messages == ["Downloading FFmpeg... 25%"]
    kw["on_done"](["ffmpeg"], [])
    assert landing.finished == [(["ffmpeg"], [])]


def test_landing_with_nothing_missing_just_launches(landing, monkeypatch):
    monkeypatch.setattr(setup_page, "install_in_background",
                        lambda *a, **k: pytest.fail("installed nothing"))
    landing._auto_install_prereqs([])
    assert landing.finished == ["launched"]
