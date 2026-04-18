"""Detect + install prerequisites: FFmpeg, Python packages, updates.

Install helpers run in the caller's thread so the dialog can show progress.
Nothing here raises — all errors flow back as ``(ok, message)`` tuples so the
UI can display them next to the relevant row.
"""

import importlib
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path


# Windows 7.1 essentials build — same one we used to bootstrap ffmpeg earlier.
_FFMPEG_WIN_URL = (
    "https://github.com/GyanD/codexffmpeg/releases/download/7.1/"
    "ffmpeg-7.1-essentials_build.zip"
)


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

REQUIRED_PACKAGES = [
    # (import name, display name, description, optional?)
    ("customtkinter", "customtkinter", "UI framework",           False),
    ("PIL",           "Pillow",        "Image processing",       False),
    ("yt_dlp",        "yt-dlp",        "Video downloads",        False),
    ("mss",           "mss",           "Screen recording",       False),
    ("tkinterdnd2",   "tkinterdnd2",   "Drag-and-drop (optional)", True),
]


def check_python_package(import_name):
    try:
        mod = importlib.import_module(import_name)
        version = getattr(mod, "__version__", None) or getattr(mod, "VERSION", "installed")
        return {"installed": True, "version": str(version)}
    except ImportError:
        return {"installed": False, "version": None}


def check_ffmpeg():
    """Delegates to the existing detector; returns same shape as others."""
    from videokidnapper.utils.ffmpeg_check import find_ffmpeg, find_ffprobe
    ffmpeg = find_ffmpeg()
    ffprobe = find_ffprobe()
    return {
        "installed": bool(ffmpeg and ffprobe),
        "path":      str(ffmpeg) if ffmpeg else None,
        "probe":     str(ffprobe) if ffprobe else None,
    }


def check_all():
    """Run every check and return a uniform dict keyed by display name."""
    results = {"FFmpeg": check_ffmpeg()}
    for import_name, display, desc, optional in REQUIRED_PACKAGES:
        status = check_python_package(import_name)
        status["optional"] = optional
        status["description"] = desc
        results[display] = status
    results["FFmpeg"]["optional"] = False
    results["FFmpeg"]["description"] = "Video/GIF encoding"
    return results


def has_any_missing(required_only=True):
    results = check_all()
    for name, info in results.items():
        if info.get("optional") and required_only:
            continue
        if not info.get("installed"):
            return True
    return False


# ---------------------------------------------------------------------------
# FFmpeg portable installer (Windows-first, falls back to terminal guidance)
# ---------------------------------------------------------------------------

def install_ffmpeg_portable(dest_dir, progress_cb=None):
    """Download the gyan.dev essentials zip and extract ffmpeg.exe/ffprobe.exe.

    Returns ``(ok, message)``.
    """
    if sys.platform != "win32":
        return False, (
            "Automatic install is Windows-only. On macOS run "
            "`brew install ffmpeg`; on Linux use your package manager."
        )

    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    zip_path = Path(tempfile.mktemp(suffix="-ffmpeg.zip"))

    try:
        def hook(block, block_size, total):
            if progress_cb and total > 0:
                frac = min(1.0, (block * block_size) / total)
                # Leave room for the extraction step at the end.
                progress_cb(frac * 0.9, f"Downloading FFmpeg... {int(frac*100)}%")

        urllib.request.urlretrieve(_FFMPEG_WIN_URL, zip_path, reporthook=hook)

        if progress_cb:
            progress_cb(0.92, "Extracting ffmpeg.exe / ffprobe.exe...")

        with zipfile.ZipFile(zip_path, "r") as zf:
            for name in zf.namelist():
                fname = os.path.basename(name)
                if fname in ("ffmpeg.exe", "ffprobe.exe"):
                    with zf.open(name) as src:
                        target = dest_dir / fname
                        with open(target, "wb") as dst:
                            shutil.copyfileobj(src, dst)

        if progress_cb:
            progress_cb(1.0, "FFmpeg installed")
        return True, str(dest_dir)
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"
    finally:
        zip_path.unlink(missing_ok=True)


def default_ffmpeg_install_dir():
    """Where ``ffmpeg_check`` looks next to the project."""
    import videokidnapper
    return Path(videokidnapper.__file__).resolve().parent.parent / "assets" / "ffmpeg" / "bin"


# ---------------------------------------------------------------------------
# pip installs
# ---------------------------------------------------------------------------

def pip_install(package, user=True, upgrade=False, timeout=240):
    cmd = [sys.executable, "-m", "pip", "install"]
    if upgrade:
        cmd.append("--upgrade")
    if user:
        cmd.append("--user")
    cmd.append(package)
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        ok = result.returncode == 0
        tail = "\n".join(
            (result.stdout or "").splitlines()[-10:]
            + (result.stderr or "").splitlines()[-10:]
        )
        return ok, tail or ("installed" if ok else "failed")
    except subprocess.TimeoutExpired:
        return False, f"pip install timed out after {timeout}s"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def pip_install_all_missing(progress_cb=None):
    """Install every required package reported missing. Returns list of results."""
    results = []
    missing = [
        (import_name, display)
        for (import_name, display, _, optional) in REQUIRED_PACKAGES
        if not optional and not check_python_package(import_name)["installed"]
    ]
    if not missing:
        return results
    for i, (import_name, display) in enumerate(missing, 1):
        if progress_cb:
            progress_cb(i / (len(missing) + 1), f"Installing {display}...")
        ok, msg = pip_install(_pip_name_for(import_name))
        results.append({"package": display, "ok": ok, "msg": msg})
    return results


def _pip_name_for(import_name):
    """Map import name to the canonical pip name (they differ for Pillow)."""
    return {"PIL": "Pillow", "yt_dlp": "yt-dlp"}.get(import_name, import_name)


# ---------------------------------------------------------------------------
# Elevated terminal
# ---------------------------------------------------------------------------

def build_install_commands(missing_ffmpeg=True, missing_pip=None):
    """Return a list of shell commands appropriate for the host OS."""
    missing_pip = missing_pip or []
    lines = []
    if sys.platform == "win32":
        if missing_ffmpeg:
            lines.append("winget install --accept-source-agreements --accept-package-agreements -e --id Gyan.FFmpeg")
        for pkg in missing_pip:
            lines.append(f"python -m pip install {pkg}")
    elif sys.platform == "darwin":
        if missing_ffmpeg:
            lines.append("brew install ffmpeg")
        for pkg in missing_pip:
            lines.append(f"python3 -m pip install --user {pkg}")
    else:
        if missing_ffmpeg:
            lines.append("sudo apt-get update && sudo apt-get install -y ffmpeg")
        for pkg in missing_pip:
            lines.append(f"pip3 install --user {pkg}")
    return lines


def open_admin_terminal(commands):
    """Open a privileged terminal pre-populated with install commands.

    Returns ``(ok, message)``. On failure, callers typically fall back to
    copying the commands to the clipboard and asking the user to run them.
    """
    if not commands:
        return False, "No commands to run."

    joined = " ; ".join(commands)

    try:
        if sys.platform == "win32":
            # RunAs triggers the UAC prompt. -NoExit keeps the window open so
            # the user can review the output.
            argv = [
                "powershell", "-NoProfile",
                "-Command",
                f"Start-Process powershell -Verb RunAs -ArgumentList '-NoExit','-Command','{joined}'",
            ]
            subprocess.Popen(argv, creationflags=subprocess.CREATE_NO_WINDOW)
            return True, "Launched elevated PowerShell."
        if sys.platform == "darwin":
            script = (
                f'tell application "Terminal" to do script '
                f'"sudo bash -c \\"{joined}\\""'
            )
            subprocess.Popen(["osascript", "-e", script])
            return True, "Launched Terminal with sudo."
        # Linux: try common terminals in order.
        for term in ("gnome-terminal", "konsole", "xfce4-terminal", "xterm"):
            if shutil.which(term):
                if term == "gnome-terminal":
                    subprocess.Popen([term, "--", "bash", "-c", f"sudo bash -c '{joined}'; exec bash"])
                else:
                    subprocess.Popen([term, "-e", f"sudo bash -c '{joined}'"])
                return True, f"Launched {term} with sudo."
        return False, "No supported terminal emulator found."
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


# ---------------------------------------------------------------------------
# Relaunch
# ---------------------------------------------------------------------------

def relaunch():
    """Restart the current Python process with the same argv."""
    os.execv(sys.executable, [sys.executable] + sys.argv)
