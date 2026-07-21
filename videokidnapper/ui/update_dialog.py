# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Install-channel-aware update prompt."""

import os
import subprocess
import threading
import webbrowser

import customtkinter as ctk

from videokidnapper.ui import theme as T
from videokidnapper.ui.theme import button
from videokidnapper.utils.github_update import build_update_plan


class UpdateDialog(ctk.CTkToplevel):
    def __init__(self, master, current_version, latest_tag, release_url, **kwargs):
        super().__init__(master, **kwargs)
        self.plan = build_update_plan(release_url=release_url)
        self.release_url = release_url
        self.title("Update VideoKidnapper")
        self.geometry("540x350")
        self.resizable(False, False)
        self.configure(fg_color=T.BG_BASE)
        self.transient(master)
        self.grab_set()

        card = ctk.CTkFrame(
            self, fg_color=T.BG_SURFACE,
            border_width=1, border_color=T.BORDER,
            corner_radius=T.RADIUS_LG,
        )
        card.pack(fill="both", expand=True, padx=14, pady=14)
        ctk.CTkLabel(
            card, text=f"VideoKidnapper {latest_tag} is ready",
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
            anchor="w",
        )
        self.status.pack(fill="x", padx=20)

        actions = ctk.CTkFrame(card, fg_color="transparent")
        actions.pack(fill="x", padx=20, pady=(14, 18))
        self.action_btn = button(
            actions, self.plan.button_text, variant="primary", width=170,
            command=self._perform_action,
        )
        self.action_btn.pack(side="left")
        secondary_text = "Copy link" if self.plan.action == "release" else "Release notes"
        secondary_command = (
            self._copy_release_link if self.plan.action == "release"
            else lambda: webbrowser.open(self.release_url)
        )
        button(
            actions, secondary_text, variant="secondary", width=125,
            command=secondary_command,
        ).pack(side="left", padx=(8, 0))
        button(
            actions, "Later", variant="ghost", width=80,
            command=self.destroy,
        ).pack(side="right")
        self.after(50, self._center)

    def _center(self):
        self.update_idletasks()
        owner = self.master.winfo_toplevel()
        x = owner.winfo_rootx() + max(0, (owner.winfo_width() - self.winfo_width()) // 2)
        y = owner.winfo_rooty() + max(0, (owner.winfo_height() - self.winfo_height()) // 2)
        self.geometry(f"+{x}+{y}")

    def _perform_action(self):
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

    def _run_command(self):
        self.action_btn.configure(state="disabled", text="Updating...")
        self.status.configure(text="Running the verified package-manager update...", text_color=T.TEXT_MUTED)
        self._update_state = {"done": False, "code": 1, "detail": ""}

        def worker():
            try:
                result = subprocess.run(
                    self.plan.command,
                    capture_output=True, text=True, timeout=600,
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
