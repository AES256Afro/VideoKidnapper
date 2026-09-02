# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0

"""Regression tests for the fail-closed macOS signing validator."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ElementTree
from pathlib import Path

import pytest


# These drive the signing shell scripts directly. Windows has no POSIX
# shell to run them with, so subprocess raises
# `OSError: [WinError 193] %1 is not a valid Win32 application` and the
# whole file fails there — which is what turned CI red on the Windows
# legs. The scripts only ever run on a maintainer's Mac anyway; the
# entitlements check below is pure XML and stays on every platform.
requires_posix_shell = pytest.mark.skipif(
    sys.platform == "win32",
    reason="POSIX shell scripts — not executable on Windows",
)

ROOT = Path(__file__).resolve().parents[1]
CHECK_SCRIPT = ROOT / "scripts" / "check-macos-signing.sh"
SETUP_SCRIPT = ROOT / "scripts" / "setup-macos-signing.sh"
ENTITLEMENTS = ROOT / "packaging" / "macos" / "entitlements.plist"


def test_entitlements_is_strict_xml() -> None:
    """Apple's signing parser rejects XML comments containing ``--``."""

    ElementTree.parse(ENTITLEMENTS)


@requires_posix_shell
def test_setup_help_documents_validated_p12_path() -> None:
    result = subprocess.run(
        [str(SETUP_SCRIPT), "--help"],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert "--p12 FILE" in result.stdout
    assert "without writing GitHub secrets" in result.stdout


@pytest.mark.skipif(shutil.which("openssl") is None, reason="openssl is required")
@requires_posix_shell
def test_validator_rejects_unrelated_private_key(tmp_path: Path) -> None:
    """A readable localhost .p12 must never be described as upload-ready."""

    key = tmp_path / "localhost.key"
    cert = tmp_path / "localhost.crt"
    bundle = tmp_path / "localhost.p12"
    password = "test-only-password"

    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-days",
            "1",
            "-subj",
            "/CN=localhost",
            "-keyout",
            str(key),
            "-out",
            str(cert),
        ],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "openssl",
            "pkcs12",
            "-export",
            "-inkey",
            str(key),
            "-in",
            str(cert),
            "-out",
            str(bundle),
            "-passout",
            f"pass:{password}",
        ],
        check=True,
        capture_output=True,
    )

    environment = os.environ.copy()
    environment["P12_PASSWORD"] = password
    result = subprocess.run(
        [str(CHECK_SCRIPT), str(bundle)],
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "unrecognised certificate type: localhost" in result.stdout
    assert "no Team ID (OU) found" in result.stdout
    assert "Ready to upload." not in result.stdout
