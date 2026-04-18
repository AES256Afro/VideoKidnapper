"""Helpers for sharing an exported file to social platforms.

None of these platforms let a third-party desktop app upload directly without
OAuth + per-platform API registration. The pragmatic shortcut used here:

1. Put the exported file on the OS clipboard so the user can paste it into
   the platform's upload dialog.
2. Open the platform's compose/upload page in the default browser.
3. The user drops or pastes the file to complete the upload.

Each platform target below specifies the compose URL and a short instruction
string shown after the button click.
"""

import os
import subprocess
import urllib.parse
import webbrowser


# URL builders: each takes the exported file path and returns (url, instructions).
def _youtube(path):
    return (
        "https://www.youtube.com/upload",
        "Click 'SELECT FILES' and paste (Ctrl+V) to upload the video.",
    )


def _instagram(_path):
    return (
        "https://www.instagram.com/",
        "Click the + (Create) button, then drop or paste the file.",
    )


def _bluesky(_path):
    return (
        "https://bsky.app/",
        "Click 'New Post', then paste (Ctrl+V) to attach the file.",
    )


def _twitter(_path):
    return (
        "https://x.com/compose/post",
        "Click the media button, then paste (Ctrl+V) to attach the file.",
    )


def _reddit(_path):
    return (
        "https://www.reddit.com/submit?type=VIDEO",
        "Drop or paste (Ctrl+V) the file into the upload area.",
    )


def _facebook(_path):
    return (
        "https://www.facebook.com/",
        "Click 'Create post' → 'Photo/Video', then paste (Ctrl+V) to attach.",
    )


SHARE_TARGETS = {
    "YouTube":   _youtube,
    "Instagram": _instagram,
    "Bluesky":   _bluesky,
    "Twitter/X": _twitter,
    "Reddit":    _reddit,
    "Facebook":  _facebook,
}


def build_share_url(platform, file_path):
    """Return ``(url, instructions)`` for the requested platform."""
    builder = SHARE_TARGETS.get(platform)
    if not builder:
        raise ValueError(f"Unknown share platform: {platform}")
    return builder(file_path)


def copy_file_to_clipboard(file_path):
    """Put the actual FILE (not its path text) on the clipboard.

    On Windows this uses PowerShell's ``Set-Clipboard -Path`` so that Ctrl+V
    pastes the file itself in Explorer and most upload dialogs. On other
    systems we fall back to copying the path as text, which at least lets the
    user paste it into a file picker's address bar.
    """
    if os.name == "nt":
        try:
            subprocess.run(
                [
                    "powershell", "-NoProfile", "-Command",
                    f"Set-Clipboard -Path '{file_path}'",
                ],
                timeout=5, check=False,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            return True
        except Exception:
            return False

    # macOS / Linux: fall back to text clipboard of the path.
    try:
        if os.uname().sysname == "Darwin":
            subprocess.run(["pbcopy"], input=file_path.encode(), timeout=3, check=False)
        else:
            subprocess.run(["xclip", "-selection", "clipboard"],
                           input=file_path.encode(), timeout=3, check=False)
        return True
    except Exception:
        return False


def open_in_browser(url):
    webbrowser.open(url)


def share(platform, file_path):
    """Copy file to clipboard, open compose page, return the instruction string."""
    url, instructions = build_share_url(platform, file_path)
    copy_file_to_clipboard(file_path)
    open_in_browser(url)
    return instructions


# For tests / UI: some platforms benefit from a URL-based share intent when
# the user is sharing a public link rather than a file. Kept separate so we
# don't accidentally open text-only intents when the user has a local file.
URL_SHARE_INTENTS = {
    "Facebook":  "https://www.facebook.com/sharer/sharer.php?u={url}",
    "Twitter/X": "https://x.com/intent/tweet?url={url}",
    "Reddit":    "https://www.reddit.com/submit?url={url}",
}


def build_url_intent(platform, url):
    template = URL_SHARE_INTENTS.get(platform)
    if not template:
        return None
    return template.format(url=urllib.parse.quote(url, safe=""))
