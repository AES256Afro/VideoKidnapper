# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Quoting tests for the elevated-terminal launcher.

``open_admin_terminal`` hands a command line to a *privileged* shell
through one or more extra interpretation layers (bash, AppleScript,
PowerShell argument lists). The commands today are fixed strings, but the
quoting must be correct against hostile input so a future change that
lets user-influenced data in (a package name, a mirror URL) cannot turn
into command injection with sudo.

These tests assert the *emitted bytes* for hostile inputs — the contract
documented above ``build_install_commands`` in
``videokidnapper/utils/prereq_check.py``.
"""
import base64
import shlex
import sys
from unittest.mock import patch

from videokidnapper.utils import prereq_check


HOSTILE = "x'; $(touch /tmp/pwned) ; echo '"


class _Spy:
    """Capture Popen argv lists without spawning anything."""

    def __init__(self):
        self.calls = []

    def __call__(self, argv, **kwargs):
        self.calls.append((argv, kwargs))

        class _Proc:
            def wait(self):
                return 0

        return _Proc()


def _extract_ps_encoded_blob(argv_string):
    """Pull the Base64 out of a Start-Process -EncodedCommand argument."""
    marker = "'-EncodedCommand','"
    start = argv_string.index(marker) + len(marker)
    end = argv_string.index("'", start)
    return argv_string[start:end]


def test_powershell_uses_encoded_command_for_hostile_input():
    spy = _Spy()
    # CREATE_NO_WINDOW only exists on Windows Pythons; provide it so the
    # branch runs on any host.
    with patch.object(sys, "platform", "win32"), \
         patch.object(prereq_check.subprocess, "CREATE_NO_WINDOW", 0,
                      create=True), \
         patch.object(prereq_check.subprocess, "Popen", spy):
        ok, _ = prereq_check.open_admin_terminal([HOSTILE])
    assert ok
    argv = spy.calls[0][0]
    assert argv[:3] == ["powershell", "-NoProfile", "-Command"]
    start_process = argv[3]
    # The hostile string must not appear raw anywhere in the argv.
    assert HOSTILE not in start_process
    assert "$(touch" not in start_process
    # ...but must round-trip exactly through the encoded command.
    blob = _extract_ps_encoded_blob(start_process)
    assert base64.b64decode(blob).decode("utf-16-le") == HOSTILE
    # The encoded blob carries only Base64 characters — nothing a quoting
    # layer could reinterpret.
    assert blob and all(c.isalnum() or c in "+/=" for c in blob)


def test_applescript_layer_escapes_quotes_and_backslashes():
    # Command containing both characters AppleScript string literals
    # cannot hold raw.
    script = prereq_check._applescript_do_script("""sudo bash -c 'a"b\\c'""")
    # In actual characters the payload became:  a\"b\\c
    # (double-quote escaped, backslash doubled).
    assert 'a\\"b\\\\c' in script
    assert script.startswith('tell application "Terminal" to do script "')
    assert script.endswith('"')


def _applescript_unescape(payload):
    """Reverse the AppleScript string-literal escaping (order matters)."""
    return payload.replace('\\\\', "\x00").replace('\\"', '"').replace("\x00", "\\")


def test_macos_launch_quotes_joined_for_bash():
    spy = _Spy()
    with patch.object(sys, "platform", "darwin"), \
         patch.object(prereq_check.subprocess, "Popen", spy):
        ok, _ = prereq_check.open_admin_terminal([HOSTILE])
    assert ok
    argv = spy.calls[0][0]
    assert argv[:2] == ["osascript", "-e"]
    script = argv[2]
    prefix = 'tell application "Terminal" to do script "'
    assert script.startswith(prefix) and script.endswith('"')
    # Peel the AppleScript layer, then parse what bash would receive the
    # same way a POSIX shell would. The payload must arrive as ONE
    # literal argument to bash -c — never as executed syntax.
    bash_cmd = _applescript_unescape(script[len(prefix):-1])
    assert shlex.split(bash_cmd) == ["sudo", "bash", "-c", HOSTILE]


def test_linux_launch_uses_shlex_quoting():
    spy = _Spy()
    def xterm_only(t):
        return "/usr/bin/xterm" if t == "xterm" else None

    with patch.object(sys, "platform", "linux"), \
         patch.object(prereq_check.shutil, "which", side_effect=xterm_only), \
         patch.object(prereq_check.subprocess, "Popen", spy):
        ok, _ = prereq_check.open_admin_terminal([HOSTILE])
    assert ok
    argv, _ = spy.calls[0]
    assert argv[:2] == ["xterm", "-e"]
    bash_cmd = argv[2]
    # The $() payload must survive as inert text inside one argument.
    assert shlex.split(bash_cmd) == ["sudo", "bash", "-c", HOSTILE]


def test_empty_command_list_is_rejected():
    ok, msg = prereq_check.open_admin_terminal([])
    assert not ok
    assert "No commands" in msg
