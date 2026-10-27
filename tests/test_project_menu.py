# SPDX-FileCopyrightText: 2026 AES256Afro <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""The project menu under the project's name, which replaced the
Projects window. Built against a stand-in menu, so no window opens."""

from types import SimpleNamespace

import pytest

from videokidnapper import app as app_module
from videokidnapper.ui.trim_tab import TrimTab


class _Menu:
    def __init__(self):
        self.entries = []

    def delete(self, first, last=None):
        self.entries.clear()

    def add_command(self, **options):
        self.entries.append(options)

    def add_separator(self):
        self.entries.append({"label": "---"})

    def labels(self):
        return [entry["label"] for entry in self.entries]


@pytest.fixture
def menu_app(monkeypatch):
    opened = []
    editor = SimpleNamespace(
        video_path=None,
        choose_and_open_project=lambda: opened.append("chooser"),
        save_project=lambda save_as=False: opened.append(("save", save_as)),
        open_project=opened.append,
    )
    app = SimpleNamespace(_project_menu=_Menu(), trim_tab=editor, opened=opened)
    app._build_project_menu = app_module.App._build_project_menu.__get__(app)
    recent = []
    monkeypatch.setattr(app_module.settings, "get_recent_projects", lambda: list(recent))
    return app, recent


def test_open_save_and_save_as_come_first(menu_app):
    app, _ = menu_app
    menu = app._build_project_menu()
    assert menu.labels() == ["Open project…", "Save", "Save as…", "---",
                             "No recent projects"]
    assert menu.entries[0]["accelerator"].endswith("O")


def test_save_waits_for_a_video(menu_app):
    app, _ = menu_app
    states = {e["label"]: e.get("state") for e in app._build_project_menu().entries}
    assert states["Save"] == states["Save as…"] == "disabled"

    app.trim_tab.video_path = "clip.mp4"
    menu = app._build_project_menu()
    states = {e["label"]: e.get("state") for e in menu.entries}
    assert states["Save"] == states["Save as…"] == "normal"
    menu.entries[2]["command"]()
    assert app.opened == [("save", True)]


def test_recent_projects_open_from_the_menu(menu_app, tmp_path):
    app, recent = menu_app
    recent += [str(tmp_path / "a" / "Cut.vidkid"), str(tmp_path / "b" / "Cut.vidkid"),
               str(tmp_path / "Trailer.vidkid")]
    menu = app._build_project_menu()
    labels = [label.strip() for label in menu.labels()[4:]]
    # Two projects with one name are told apart by their folder.
    assert labels == ["Recent projects", "Cut  (a)", "Cut  (b)", "Trailer"]
    menu.entries[-1]["command"]()
    assert app.opened == [str(tmp_path / "Trailer.vidkid")]


def test_the_project_hub_is_the_import_workspace():
    shown = []
    editor = SimpleNamespace(_show_workspace=shown.append)
    TrimTab.open_project_hub(editor)
    assert shown == ["import"]
