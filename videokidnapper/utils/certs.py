# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Give the interpreter a certificate store when it has none.

Python from python.org on macOS ships without root certificates and
does not read the system keychain. Until the user runs the installer's
"Install Certificates.command" (most never do), every HTTPS connection
fails with ``CERTIFICATE_VERIFY_FAILED``: the FFmpeg download, yt-dlp,
the update check. Running from source on such a Python, the app could
not download anything.

The fix is the one Python's own installer applies: point OpenSSL at
certifi's bundle of Mozilla's roots. It is done through the
``SSL_CERT_FILE`` environment variable so it reaches everything in this
process (``urllib``, yt-dlp, ``ssl.create_default_context``) and every
child process (pip, a yt-dlp update).

Only macOS is touched, and only when the interpreter really has no
store. Linux Pythons use the distribution's certificates and Windows
Pythons read the system store, which may hold a company's own root;
overriding either would break more than it fixed. An ``SSL_CERT_FILE``
or ``SSL_CERT_DIR`` the user already set is always respected.
"""

import os
import ssl
import sys


def interpreter_has_ca_store():
    """True when OpenSSL can find a certificate file or directory."""
    paths = ssl.get_default_verify_paths()
    if paths.cafile and os.path.isfile(paths.cafile):
        return True
    if paths.capath and os.path.isdir(paths.capath):
        try:
            return any(os.scandir(paths.capath))
        except OSError:
            return False
    return False


def ssl_context():
    """An SSL context that verifies with a store this Python can find.

    ``urllib`` builds its default context once, on first use, so a store
    supplied later through the environment is not seen by it. Code that
    downloads should pass this context explicitly instead of relying on
    the process-wide default.
    """
    bundle = ensure_ca_bundle() or os.environ.get("SSL_CERT_FILE")
    if bundle and os.path.isfile(bundle):
        return ssl.create_default_context(cafile=bundle)
    return ssl.create_default_context()


def ensure_ca_bundle():
    """Set ``SSL_CERT_FILE`` to certifi's bundle if this Python needs it.

    Returns the path that was set, or ``None`` when nothing was changed:
    not macOS, a store already present, the user's own setting, or
    certifi not installed. Safe to call more than once. Call it before
    the first network use: ``urllib`` keeps the SSL context it builds on
    first use, so a store that appears afterwards is not picked up by
    connections made through the default opener.
    """
    if sys.platform != "darwin":
        return None
    if os.environ.get("SSL_CERT_FILE") or os.environ.get("SSL_CERT_DIR"):
        return None
    if interpreter_has_ca_store():
        return None
    try:
        import certifi
    except ImportError:
        return None
    bundle = certifi.where()
    if not os.path.isfile(bundle):
        return None
    os.environ["SSL_CERT_FILE"] = bundle
    return bundle
