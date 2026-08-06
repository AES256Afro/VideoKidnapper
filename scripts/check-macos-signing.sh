#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
#
# Validate a Developer ID .p12 BEFORE uploading it as a GitHub secret.
#
#   ./scripts/check-macos-signing.sh ~/Desktop/DeveloperID.p12
#
# Everything runs locally. No secret is printed, written, or uploaded —
# the password is read with a hidden prompt and only handed to openssl
# on stdin, never as an argv the process list could expose.
#
# The check that matters most is #2: Keychain Access will happily export
# a .p12 containing only the certificate if you export from the wrong
# view, and such a file imports without error but cannot sign anything.
# In CI that surfaces much later as a confusing codesign failure.

set -uo pipefail

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[0;33m'; DIM='\033[2m'; OFF='\033[0m'
ok()   { printf "  ${GREEN}✓${OFF} %s\n" "$1"; }
bad()  { printf "  ${RED}✗${OFF} %s\n" "$1"; FAILED=$((FAILED + 1)); }
warn() { printf "  ${YELLOW}!${OFF} %s\n" "$1"; }
info() { printf "    ${DIM}%s${OFF}\n" "$1"; }

FAILED=0
P12="${1:-}"

if [ -z "$P12" ]; then
    echo "usage: $0 <path-to-.p12>" >&2
    exit 2
fi
if [ ! -f "$P12" ]; then
    echo "error: no such file: $P12" >&2
    exit 2
fi

echo
echo "Checking $(basename "$P12")"
echo

# Password: prefer the env var (for non-interactive use), else prompt.
if [ -n "${P12_PASSWORD:-}" ]; then
    PW="$P12_PASSWORD"
else
    printf "  .p12 export password: "
    read -rs PW
    echo
    echo
fi

# The password goes in on stdin, never as `-passin pass:...` — argv is
# world-readable via ps(1) for the lifetime of the process.
#
# OpenSSL 3 also rejects the older RC2 encryption that some Keychain
# Access versions still emit; -legacy re-enables it. Try modern first.
DUMP="$(printf '%s\n' "$PW" | openssl pkcs12 -in "$P12" -nodes -passin stdin 2>/dev/null)"
if [ -z "$DUMP" ]; then
    DUMP="$(printf '%s\n' "$PW" | openssl pkcs12 -in "$P12" -nodes -legacy -passin stdin 2>/dev/null)"
    [ -n "$DUMP" ] && warn "needed OpenSSL -legacy mode (old export format; still fine for CI)"
fi

# --- 1. Password / readability -------------------------------------------
if [ -z "$DUMP" ]; then
    bad "could not open the .p12 — wrong password, or the file is not a PKCS#12"
    info "re-export from Keychain Access and note the password exactly"
    echo
    exit 1
fi
ok "opened the .p12 (password correct)"

# --- 2. Private key present (THE critical check) --------------------------
if printf '%s' "$DUMP" | grep -q -- "-----BEGIN PRIVATE KEY-----\|-----BEGIN RSA PRIVATE KEY-----\|-----BEGIN EC PRIVATE KEY-----"; then
    ok "contains a private key"
else
    bad "NO PRIVATE KEY — this file cannot sign anything"
    info "In Keychain Access choose the 'My Certificates' category, not"
    info "'Certificates'. Expand the triangle next to the certificate; if"
    info "no key is nested under it, the key is missing from this Mac and"
    info "you must reissue the certificate."
    echo
    exit 1
fi

# --- 3. Certificate type --------------------------------------------------
CERT="$(printf '%s' "$DUMP" | openssl x509 2>/dev/null)"
if [ -z "$CERT" ]; then
    bad "no X.509 certificate inside"
    echo; exit 1
fi
SUBJECT="$(printf '%s' "$CERT" | openssl x509 -noout -subject -nameopt multiline 2>/dev/null)"
CN="$(printf '%s' "$SUBJECT" | awk -F' = ' '/commonName/{print $2}')"
OU="$(printf '%s' "$SUBJECT" | awk -F' = ' '/organizationalUnitName/{print $2}')"

case "$CN" in
    "Developer ID Application:"*)
        ok "certificate type: Developer ID Application" ;;
    "Apple Development:"*|"Apple Distribution:"*|"Mac Developer:"*)
        bad "wrong certificate type: ${CN%%:*}"
        info "Distributing outside the App Store needs 'Developer ID"
        info "Application'. Create one at developer.apple.com → Certificates."
        ;;
    "3rd Party Mac Developer"*|"Developer ID Installer:"*)
        bad "wrong certificate type: $CN"
        info "'Developer ID Installer' signs .pkg files. You need"
        info "'Developer ID Application' for a .app/.dmg."
        ;;
    *)
        warn "unrecognised certificate type: ${CN:-<none>}" ;;
esac

# --- 4. Expiry ------------------------------------------------------------
NOT_AFTER="$(printf '%s' "$CERT" | openssl x509 -noout -enddate 2>/dev/null | cut -d= -f2)"
if printf '%s' "$CERT" | openssl x509 -noout -checkend 0 >/dev/null 2>&1; then
    if printf '%s' "$CERT" | openssl x509 -noout -checkend 2592000 >/dev/null 2>&1; then
        ok "valid until $NOT_AFTER"
    else
        warn "expires within 30 days ($NOT_AFTER)"
    fi
else
    bad "EXPIRED on $NOT_AFTER"
fi

# --- 5. Team ID -----------------------------------------------------------
if [ -n "$OU" ]; then
    ok "Team ID: $OU"
    info "use this for the MACOS_NOTARY_TEAM_ID secret"
else
    warn "no Team ID (OU) found in the certificate"
fi

# --- 6. The identity string codesign will use -----------------------------
echo
if [ -n "$CN" ]; then
    echo "  Signing identity the build will resolve:"
    printf "    ${DIM}%s${OFF}\n" "$CN"
fi

# --- 7. Is the key usable from this Mac's keychain? ------------------------
echo
if command -v security >/dev/null 2>&1; then
    if security find-identity -v -p codesigning 2>/dev/null | grep -q "Developer ID Application"; then
        ok "a Developer ID identity is also usable from your login keychain"
        info "local signed builds will work too"
    else
        warn "no Developer ID identity in your login keychain"
        info "only affects local builds; CI imports the .p12 itself"
    fi
fi

# --- Result ---------------------------------------------------------------
echo
if [ "$FAILED" -eq 0 ]; then
    printf "  ${GREEN}Ready to upload.${OFF}\n\n"
    cat <<EOF
  base64 -i "$P12" | gh secret set MACOS_CERT_P12_BASE64
  gh secret set MACOS_CERT_PASSWORD
  gh secret set MACOS_NOTARY_APPLE_ID
  gh secret set MACOS_NOTARY_TEAM_ID     # ${OU:-<team id>}
  gh secret set MACOS_NOTARY_PASSWORD    # app-specific password

EOF
    exit 0
fi

printf "  ${RED}%d problem(s) — fix before uploading.${OFF}\n\n" "$FAILED"
exit 1
