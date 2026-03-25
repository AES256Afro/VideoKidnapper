import customtkinter as ctk

from videokidnapper.config import APP_NAME, APP_VERSION, WINDOW_SIZE, MIN_WINDOW_SIZE
from videokidnapper.utils.ffmpeg_check import check_ffmpeg


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.title(f"{APP_NAME} v{APP_VERSION}")
        self.geometry(WINDOW_SIZE)
        self.minsize(*MIN_WINDOW_SIZE)

        self.ffmpeg_path, self.ffprobe_path = check_ffmpeg()

        if not self.ffmpeg_path:
            self._show_ffmpeg_warning()
            return

        self._build_ui()

    def _build_ui(self):
        # Header
        header = ctk.CTkFrame(self, height=60, corner_radius=0, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=(15, 5))
        header.pack_propagate(False)

        title_label = ctk.CTkLabel(
            header, text=f"  {APP_NAME}",
            font=ctk.CTkFont(size=24, weight="bold"),
        )
        title_label.pack(side="left")

        version_label = ctk.CTkLabel(
            header, text=f"v{APP_VERSION}",
            font=ctk.CTkFont(size=12),
            text_color="gray",
        )
        version_label.pack(side="left", padx=(8, 0), pady=(8, 0))

        # Tabs
        self.tabview = ctk.CTkTabview(self, corner_radius=10)
        self.tabview.pack(fill="both", expand=True, padx=20, pady=(5, 20))

        self.tabview.add("Trim Video")
        self.tabview.add("URL Download")
        self.tabview.add("Debug")

        from videokidnapper.ui.trim_tab import TrimTab
        from videokidnapper.ui.url_tab import UrlTab
        from videokidnapper.ui.debug_tab import DebugTab

        # Debug tab first so it captures logs from other tabs during init
        self.debug_tab = DebugTab(self.tabview.tab("Debug"), self)
        self.debug_tab.pack(fill="both", expand=True)

        self.trim_tab = TrimTab(self.tabview.tab("Trim Video"), self)
        self.trim_tab.pack(fill="both", expand=True)

        self.url_tab = UrlTab(self.tabview.tab("URL Download"), self)
        self.url_tab.pack(fill="both", expand=True)

    def _show_ffmpeg_warning(self):
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.place(relx=0.5, rely=0.5, anchor="center")

        icon_label = ctk.CTkLabel(
            frame, text="FFmpeg Not Found",
            font=ctk.CTkFont(size=22, weight="bold"),
        )
        icon_label.pack(pady=(0, 10))

        msg = (
            "VideoKidnapper requires FFmpeg to process video and create GIFs.\n\n"
            "Please install FFmpeg:\n"
            "1. Download from https://www.gyan.dev/ffmpeg/builds/\n"
            "2. Extract and add the bin/ folder to your system PATH\n"
            "   OR place ffmpeg.exe in assets/ffmpeg/bin/ next to this project\n"
            "3. Restart VideoKidnapper"
        )
        msg_label = ctk.CTkLabel(
            frame, text=msg,
            font=ctk.CTkFont(size=14),
            justify="left",
        )
        msg_label.pack(pady=(0, 20))

        quit_btn = ctk.CTkButton(
            frame, text="Exit", command=self.destroy,
            width=120, height=36,
        )
        quit_btn.pack()
