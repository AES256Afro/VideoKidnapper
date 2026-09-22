# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""A python.org Python on macOS gets certifi's roots; nothing else changes."""

import os
import ssl
import sys

import pytest

from videokidnapper.utils import certs

certifi = pytest.importorskip("certifi")


@pytest.fixture
def clean_env(monkeypatch):
    monkeypatch.delenv("SSL_CERT_FILE", raising=False)
    monkeypatch.delenv("SSL_CERT_DIR", raising=False)


def _no_store(monkeypatch):
    monkeypatch.setattr(ssl, "get_default_verify_paths", lambda: ssl.DefaultVerifyPaths(
        None, None, "SSL_CERT_FILE", "/nonexistent/cert.pem", "SSL_CERT_DIR", "/nonexistent"))


def test_mac_python_without_a_store_gets_certifi(monkeypatch, clean_env):
    monkeypatch.setattr(sys, "platform", "darwin")
    _no_store(monkeypatch)
    assert certs.ensure_ca_bundle() == certifi.where()
    assert os.environ["SSL_CERT_FILE"] == certifi.where()


def test_a_python_with_a_store_is_left_alone(monkeypatch, clean_env, tmp_path):
    monkeypatch.setattr(sys, "platform", "darwin")
    pem = tmp_path / "cert.pem"
    pem.write_text("x")
    monkeypatch.setattr(ssl, "get_default_verify_paths", lambda: ssl.DefaultVerifyPaths(
        str(pem), None, "SSL_CERT_FILE", str(pem), "SSL_CERT_DIR", None))
    assert certs.ensure_ca_bundle() is None
    assert "SSL_CERT_FILE" not in os.environ


def test_users_own_setting_wins(monkeypatch, clean_env):
    monkeypatch.setattr(sys, "platform", "darwin")
    _no_store(monkeypatch)
    monkeypatch.setenv("SSL_CERT_FILE", "/my/company/roots.pem")
    assert certs.ensure_ca_bundle() is None
    assert os.environ["SSL_CERT_FILE"] == "/my/company/roots.pem"


@pytest.mark.parametrize("platform", ["win32", "linux"])
def test_other_platforms_are_never_touched(monkeypatch, clean_env, platform):
    """Windows reads the system store and Linux the distro's; a company
    root there must keep working."""
    monkeypatch.setattr(sys, "platform", platform)
    _no_store(monkeypatch)
    assert certs.ensure_ca_bundle() is None
    assert "SSL_CERT_FILE" not in os.environ


def test_cli_bootstraps_before_running(monkeypatch):
    """main() sets the store up before any code can hit the network."""
    calls = []
    monkeypatch.setattr(certs, "ensure_ca_bundle", lambda: calls.append("ca"))
    from videokidnapper import cli
    monkeypatch.setattr(sys, "argv", ["videokidnapper", "--version"])
    with pytest.raises(SystemExit):
        cli.main()
    assert calls == ["ca"]


def test_download_context_carries_certifi_on_a_storeless_mac(monkeypatch, clean_env):
    monkeypatch.setattr(sys, "platform", "darwin")
    _no_store(monkeypatch)
    ctx = certs.ssl_context()
    assert ctx.verify_mode == ssl.CERT_REQUIRED
    assert len(ctx.get_ca_certs()) > 100   # Mozilla's roots are loaded
