# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Install-channel-aware update prompt.

Windows Setup, winget and portable installs update in place: "Restart to
update" downloads the new build with a progress bar, then the app closes,
installs it and opens again (utils/self_update.py). Other installs keep
their own route: the Store, a package manager, or the release page.
"""

import os
import subprocess
import threading
import webbrowser

import customtkinter as ctk

from videokidnapper.ui import theme as T
from videokidnapper.ui.theme import button
from videokidnapper.utils.github_update import build_update_plan, is_newer


def _mb(n):
    return f"{n / 1_000_000:.0f} MB"


class UpdateDialog(ctk.CTkToplevel):
    def __init__(self, master, current_version, latest_tag, release_url, **kwargs):
        super().__init__(master, **kwargs)
        self.plan = build_update_plan(release_url=release_url)
        self.release_url = release_url
        self.current_version = current_version
        self.title("Update VideoKidnapper")
        self.geometry("540x350")
        self.resizable(False, False)
        self.configure(fg_color=T.BG_BASE)
        self.transient(master)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._close)

        self._cancel = threading.Event()
        self._downloading = False
        self._downloaded = None  # path of a verified download, kept for a retry

        card = ctk.CTkFrame(
            self, fg_color=T.BG_SURFACE,
            border_width=1, border_color=T.BORDER,
            corner_radius=T.RADIUS_LG,
        )
        card.pack(fill="both", expand=True, padx=14, pady=14)
        installs_itself = self.plan.action == "install"
        title = (f"Restart to install VideoKidnapper {latest_tag}?" if installs_itself
                 else f"VideoKidnapper {latest_tag} is ready")
        ctk.CTkLabel(
            card, text=title,
            font=T.font(T.SIZE_XL, "bold"), text_color=T.TEXT,
        ).pack(anchor="w", padx=20, pady=(20, 4))
        ctk.CTkLabel(
            card, text=f"Installed: v{current_version}  ·  Route: {self.plan.label}",
            font=T.font(T.SIZE_SM), text_color=T.TEXT_DIM,
        ).pack(anchor="w", padx=20)
        ctk.CTkLabel(
            card, text=self.plan.summary,
            font=T.font(T.SIZE_MD), text_color=T.TEXT_MUTED,
            justify="left", wraplength=480,
        ).pack(anchor="w", padx=20, pady=(18, 8))

        if installs_itself:
            self.progress = ctk.CTkProgressBar(
                card, height=10, corner_radius=5,
                progress_color=T.ACCENT, fg_color=T.BG_RAISED,
            )
            self.progress.set(0)
            self.progress.pack(fill="x", padx=20, pady=(14, 12))
            initial_status = "Nothing downloads until you choose Restart to update."
        else:
            self.command_box = ctk.CTkTextbox(
                card, height=70, fg_color=T.BG_RAISED,
                border_width=1, border_color=T.BORDER,
                text_color=T.TEXT, font=T.font(T.SIZE_SM, mono=True),
                corner_radius=T.RADIUS_SM,
            )
            display = " ".join(self.plan.command) if self.plan.command else self.plan.copy_text
            self.command_box.insert("1.0", display)
            self.command_box.configure(state="disabled")
            self.command_box.pack(fill="x", padx=20, pady=(4, 10))
            initial_status = (
                "Your project remains open while the updater runs."
                if self.plan.action == "run" else
                "Nothing changes until you choose an update action."
            )
        self.status = ctk.CTkLabel(
            card, text=initial_status,
            font=T.font(T.SIZE_SM), text_color=T.TEXT_DIM,
            anchor="w", justify="left", wraplength=480,
        )
        self.status.pack(fill="x", padx=20)

        actions = ctk.CTkFrame(card, fg_color="transparent")
        actions.pack(fill="x", padx=20, pady=(14, 18))
        self.action_btn = button(
            actions, self.plan.button_text, variant="primary", width=170,
            command=self._perform_action,
        )
        self.action_btn.pack(side="left")
        if self.plan.action == "release":
            secondary_text, secondary_command = "Copy link", self._copy_release_link
        else:
            secondary_text = "What's new" if installs_itself else "Release notes"
            secondary_command = lambda: webbrowser.open(self.release_url)  # noqa: E731
        button(
            actions, secondary_text, variant="secondary", width=125,
            command=secondary_command,
        ).pack(side="left", padx=(8, 0))
        self.later_btn = button(
            actions, "Later", variant="ghost", width=80,
            command=self._close,
        )
        self.later_btn.pack(side="right")
        self.after(50, self._center)

    def _center(self):
        self.update_idletasks()
        owner = self.master.winfo_toplevel()
        x = owner.winfo_rootx() + max(0, (owner.winfo_width() - self.winfo_width()) // 2)
        y = owner.winfo_rooty() + max(0, (owner.winfo_height() - self.winfo_height()) // 2)
        self.geometry(f"+{x}+{y}")

    def _close(self):
        """Later / Cancel / the window's X: stop any download, then close."""
        if self._downloading:
            self._cancel.set()
            self.status.configure(text="Cancelling the download...", text_color=T.TEXT_MUTED)
            return
        self.destroy()

    def _perform_action(self):
        if self.plan.action == "install":
            self._start_self_update()
            return
        if self.plan.action == "store":
            try:
                if os.name == "nt":
                    os.startfile(self.plan.copy_text)  # type: ignore[attr-defined]
                else:
                    webbrowser.open(self.plan.copy_text)
                self.status.configure(text="Store updates opened.", text_color=T.SUCCESS)
            except Exception as exc:
                self.status.configure(text=f"Could not open the Store: {exc}", text_color=T.DANGER)
            return
        if self.plan.action == "release":
            webbrowser.open(self.release_url)
            self.status.configure(text="Release download opened.", text_color=T.SUCCESS)
            return
        if self.plan.action == "copy":
            self.clipboard_clear()
            self.clipboard_append(self.plan.copy_text)
            self.status.configure(text="Update command copied.", text_color=T.SUCCESS)
            return
        self._run_command()

    def _copy_release_link(self):
        self.clipboard_clear()
        self.clipboard_append(self.release_url)
        self.status.configure(text="Release link copied.", text_color=T.SUCCESS)

    # ------------------------------------------------------------------
    # In-place update (Setup, winget, portable)
    # ------------------------------------------------------------------
    def _start_self_update(self):
        if self._downloaded is not None:
            self._install(self._downloaded)
            return
        from videokidnapper.utils import self_update

        self._cancel.clear()
        self._downloading = True
        self.action_btn.configure(state="disabled", text="Downloading...")
        self.later_btn.configure(text="Cancel")
        self.status.configure(text="Checking the latest release...", text_color=T.TEXT_MUTED)
        # Written by the worker, read by _poll_download on the Tk thread.
        state = self._dl = {"done": 0, "total": 0, "path": None, "error": None,
                            "fallback": False, "finished": False}
        channel, current = self.plan.channel, self.current_version

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

                state["path"] = self_update.download(asset, progress=progress,
                                                     cancel=self._cancel)
            except self_update.UpdateCancelled:
                state["error"] = "Download cancelled."
            except self_update.UpdateError as exc:
                state["error"] = str(exc)
            except Exception as exc:  # never let the worker die silently
                state["error"] = f"The update failed: {exc}"
            finally:
                state["finished"] = True

        threading.Thread(target=worker, daemon=True).start()
        self.after(100, self._poll_download)

    def _poll_download(self):
        if not self.winfo_exists():
            return
        state = self._dl
        if state["total"]:
            self.progress.set(min(1.0, state["done"] / state["total"]))
            self.status.configure(
                text=f"Downloading {_mb(state['done'])} of {_mb(state['total'])}...",
                text_color=T.TEXT_MUTED,
            )
        if not state["finished"]:
            self.after(100, self._poll_download)
            return
        self._downloading = False
        self.later_btn.configure(text="Later")
        if state["error"]:
            if state["fallback"]:
                webbrowser.open(self.release_url)
            cancelled = self._cancel.is_set()
            self.progress.set(0)
            self.action_btn.configure(state="normal", text=self.plan.button_text)
            self.status.configure(
                text=state["error"],
                text_color=T.TEXT_MUTED if cancelled else T.DANGER,
            )
            return
        self._downloaded = state["path"]
        self.progress.set(1.0)
        self._install(self._downloaded)

    def _install(self, path):
        self.action_btn.configure(state="disabled", text="Restarting...")
        self.status.configure(text="Closing VideoKidnapper to install the update...",
                              text_color=T.TEXT_MUTED)
        self.update_idletasks()
        installer = getattr(self.master, "install_downloaded_update", None)
        if installer is None:
            problem = "This window can't restart the app. Close it and run the update yourself."
        else:
            # Returns only when it did NOT exit (the user kept the project
            # open, or the installer couldn't start).
            problem = installer(path, self.plan.channel)
        if not self.winfo_exists():
            return
        self.action_btn.configure(state="normal", text=self.plan.button_text)
        self.status.configure(text=problem or "", text_color=T.DANGER)

    # ------------------------------------------------------------------
    # Package-manager command (pip)
    # ------------------------------------------------------------------
    def _run_command(self):
        self.action_btn.configure(state="disabled", text="Updating...")
        self.status.configure(text="Running the verified package-manager update...", text_color=T.TEXT_MUTED)
        self._update_state = {"done": False, "code": 1, "detail": ""}

        def worker():
            try:
                result = subprocess.run(
                    self.plan.command,
                    capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600,
                    creationflags=(
                        subprocess.CREATE_NO_WINDOW
                        if os.name == "nt" else 0
                    ),
                )
                detail = (result.stdout or result.stderr or "").strip()
                self._update_state.update(
                    done=True, code=result.returncode, detail=detail,
                )
            except Exception as exc:
                self._update_state.update(done=True, code=1, detail=str(exc))

        threading.Thread(target=worker, daemon=True).start()
        self.after(150, self._poll_command)

    def _poll_command(self):
        if not self.winfo_exists():
            return
        state = self._update_state
        if not state["done"]:
            self.after(150, self._poll_command)
            return
        self._command_finished(state["code"], state["detail"])

    def _command_finished(self, return_code, detail):
        if not self.winfo_exists():
            return
        self.action_btn.configure(state="normal", text=self.plan.button_text)
        if return_code == 0:
            self.status.configure(
                text="Update completed. Save your project and restart VideoKidnapper.",
                text_color=T.SUCCESS,
            )
            return
        concise = detail.splitlines()[-1][:120] if detail else "Unknown package-manager error"
        self.status.configure(text=f"Update did not finish: {concise}", text_color=T.DANGER)
