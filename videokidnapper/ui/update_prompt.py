# SPDX-FileCopyrightText: 2026 AES256Afro <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""The update offer, asked in the main window's banner.

VideoKidnapper is one window with no popups, so the update is offered in
the banner under the header (``ui.studio.banner``) instead of a window
of its own.

Windows Setup, winget and portable installs update in place: "Restart to
update" downloads the new build with a progress bar in the banner, then
the app closes, installs it and opens again (``utils/self_update.py``).
Other installs keep their own route: the Store, a package manager, or
the release page.
"""

import os
import subprocess
import threading
import webbrowser

from videokidnapper.utils.github_update import build_update_plan, is_newer

#: One update question at a time: asking again replaces it in place.
KEY = "update"
_POLL_MS = 100


def _mb(n):
    return f"{n / 1_000_000:.0f} MB"


class UpdatePrompt:
    """Offers one release and carries it through to the install.

    Keeps its state between showings: a download that finished (and was
    verified) is not fetched again when the user picks "Later" and comes
    back to it.
    """

    def __init__(self, app, current_version, latest_tag, release_url, plan=None):
        self.app = app
        self.current_version = current_version
        self.tag = latest_tag
        self.release_url = release_url
        self.plan = plan or build_update_plan(release_url=release_url)
        self.prompt = None
        self._cancel = threading.Event()
        self._downloading = False
        self._downloaded = None   # path of a verified download
        self._running_command = False

    # ------------------------------------------------------------------
    def show(self):
        """Ask (again). Shows the current state if work is under way."""
        if self._downloading or self._running_command:
            return
        if self._downloaded is not None:
            self._ready()
            return
        action = self.plan.action
        name = f"VideoKidnapper {self.tag}"
        if action == "install":
            self._ask(f"{name} is available",
                      "Restart to update downloads it, closes the app, installs it "
                      "and opens it again. You can save your project first.",
                      [("Restart to update", "primary", self._start_download, False),
                       ("What's new", "secondary", self._open_release, False),
                       ("Later", "ghost", None)])
        elif action == "store":
            self._ask(f"{name} is available", self.plan.summary,
                      [("Open the Store", "primary", self._open_store),
                       ("Later", "ghost", None)])
        elif action == "release":
            self._ask(f"{name} is available", self.plan.summary,
                      [("Download", "primary", self._open_release),
                       ("Copy link", "secondary", self._copy_link, False),
                       ("Later", "ghost", None)])
        elif action == "copy":
            self._ask(f"{name} is available",
                      f"{self.plan.summary}  {self._command_text()}",
                      [("Copy command", "primary", self._copy_command, False),
                       ("Release notes", "secondary", self._open_release, False),
                       ("Later", "ghost", None)])
        else:
            self._ask(f"{name} is available", self.plan.summary,
                      [(self.plan.button_text, "primary", self._run_command, False),
                       ("Release notes", "secondary", self._open_release, False),
                       ("Later", "ghost", None)])

    def _ask(self, message, detail, buttons, tone="info", progress=None, dismiss=True):
        self.prompt = self.app.banner.ask(
            message, buttons=buttons, detail=detail, dismiss=dismiss,
            tone=tone, progress=progress, key=KEY,
        )
        return self.prompt

    def _say(self, detail, tone=None):
        """Change the detail line of the open prompt, if there is one."""
        if self.prompt is not None and self.prompt.is_open:
            kwargs = {"detail": detail}
            if tone is not None:
                kwargs["tone"] = tone
            self.prompt.update(**kwargs)

    # ------------------------------------------------------------------
    # Simple routes
    # ------------------------------------------------------------------
    def _open_release(self):
        webbrowser.open(self.release_url)

    def _open_store(self):
        try:
            if os.name == "nt":
                os.startfile(self.plan.copy_text)  # type: ignore[attr-defined]
            else:
                webbrowser.open(self.plan.copy_text)
        except Exception as exc:
            self._ask("Couldn't open the Store", str(exc), [("Later", "ghost", None)],
                      tone="warn")

    def _copy(self, text):
        self.app.clipboard_clear()
        self.app.clipboard_append(text)

    def _copy_link(self):
        self._copy(self.release_url)
        self._say("Release link copied.", tone="success")

    def _command_text(self):
        return " ".join(self.plan.command) if self.plan.command else self.plan.copy_text

    def _copy_command(self):
        self._copy(self._command_text())
        self._say("Update command copied.", tone="success")

    # ------------------------------------------------------------------
    # In-place update (Setup, winget, portable)
    # ------------------------------------------------------------------
    def _start_download(self):
        if self._downloading:
            return
        from videokidnapper.utils import self_update

        self._cancel.clear()
        self._downloading = True
        self._ask(f"Downloading VideoKidnapper {self.tag}…",
                  "Checking the latest release…",
                  [("Cancel", "ghost", self._cancel_download, False)],
                  progress=0.0, dismiss=None)
        # Written by the worker, read by _poll on the Tk thread.
        state = {"done": 0, "total": 0, "path": None, "error": None,
                 "fallback": False, "finished": False}
        channel, current = self.plan.channel, self.current_version
        cancel = self._cancel

        def worker():
            try:
                release = self_update.fetch_release()
                if release is None:
                    raise self_update.UpdateError(
                        "Couldn't reach GitHub. Check your connection and try again.")
                if not is_newer(release.tag, current):
                    raise self_update.UpdateError(f"v{current} is already the latest version.")
                asset = self_update.pick_asset(release, channel)
                if asset is None:
                    state["fallback"] = True
                    raise self_update.UpdateError(
                        "This release can't be installed automatically, so its "
                        "download page is open in your browser.")
                state["total"] = asset.size

                def progress(done, total):
                    state["done"], state["total"] = done, total

                state["path"] = self_update.download(asset, progress=progress, cancel=cancel)
            except self_update.UpdateCancelled:
                state["error"] = "Download cancelled."
            except self_update.UpdateError as exc:
                state["error"] = str(exc)
            except Exception as exc:  # never let the worker die silently
                state["error"] = f"The update failed: {exc}"
            finally:
                state["finished"] = True

        threading.Thread(target=worker, daemon=True, name="update-download").start()
        self.app.after(_POLL_MS, self._poll, state)

    def _cancel_download(self):
        self._cancel.set()
        self._say("Cancelling the download…")

    def _poll(self, state):
        if state["total"] and self.prompt is not None:
            self.prompt.set_progress(
                min(1.0, state["done"] / state["total"]),
                detail=f"{_mb(state['done'])} of {_mb(state['total'])}",
            )
        if not state["finished"]:
            self.app.after(_POLL_MS, self._poll, state)
            return
        self._downloading = False
        if state["error"]:
            if state["fallback"]:
                self._open_release()
            cancelled = self._cancel.is_set()
            self._ask("The update didn't download" if not cancelled else "Download cancelled",
                      None if cancelled else state["error"],
                      [("Try again", "primary", self._start_download, False),
                       ("Later", "ghost", None)],
                      tone="info" if cancelled else "warn")
            return
        self._downloaded = state["path"]
        self._install()

    def _install(self):
        """Close the app safely, then hand over to the installer.

        The save and stop-the-export questions are asked in this same
        banner, so the update prompt steps aside for them first.
        """
        if self.prompt is not None:
            self.prompt.close()
        installer = getattr(self.app, "install_downloaded_update", None)
        if installer is None:
            self._install_failed("This window can't restart the app. "
                                 "Close it and run the update yourself.")
            return
        installer(self._downloaded, self.plan.channel,
                  on_cancel=self._ready, on_error=self._install_failed)

    def _ready(self):
        self._ask(f"VideoKidnapper {self.tag} is downloaded",
                  "Restart to install it when you're ready.",
                  [("Restart to update", "primary", self._install),
                   ("Later", "ghost", None)])

    def _install_failed(self, message):
        self._ask("The update couldn't start", message,
                  [("Try again", "primary", self._install),
                   ("Download page", "secondary", self._open_release, False),
                   ("Later", "ghost", None)],
                  tone="warn")

    # ------------------------------------------------------------------
    # Package-manager command (pip)
    # ------------------------------------------------------------------
    def _run_command(self):
        if self._running_command:
            return
        self._running_command = True
        self._ask("Updating VideoKidnapper…",
                  "Running the verified package-manager update. You can keep working.",
                  [], dismiss=None)
        state = {"done": False, "code": 1, "detail": ""}
        command = list(self.plan.command)

        def worker():
            try:
                result = subprocess.run(
                    command, capture_output=True,
                    text=True, encoding="utf-8", errors="replace", timeout=600,
                    creationflags=(subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0),
                )
                detail = (result.stdout or result.stderr or "").strip()
                state.update(done=True, code=result.returncode, detail=detail)
            except Exception as exc:
                state.update(done=True, code=1, detail=str(exc))

        threading.Thread(target=worker, daemon=True, name="update-command").start()
        self.app.after(150, self._poll_command, state)

    def _poll_command(self, state):
        if not state["done"]:
            self.app.after(150, self._poll_command, state)
            return
        self._running_command = False
        if state["code"] == 0:
            restart = getattr(self.app, "_restart_app", None)
            buttons = [("Restart now", "primary", restart)] if restart else []
            self._ask("VideoKidnapper is updated",
                      "Restart it to use the new version.",
                      buttons + [("Later", "ghost", None)], tone="success")
            return
        detail = state["detail"]
        concise = detail.splitlines()[-1][:120] if detail else "Unknown package-manager error"
        self._ask("The update didn't finish", concise,
                  [("Try again", "primary", self._run_command, False),
                   ("Later", "ghost", None)],
                  tone="warn")
