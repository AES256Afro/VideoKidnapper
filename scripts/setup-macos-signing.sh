#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
#
# One command to put the macOS signing + notarization secrets in place.
#
#   ./scripts/setup-macos-signing.sh              # do it
#   ./scripts/setup-macos-signing.sh --dry-run    # show what it would do
#   ./scripts/setup-macos-signing.sh --p12 FILE   # use one validated export
#
# It exports the .p12 for you with `security export`, so you never have
# to navigate Keychain Access — the step people get wrong by exporting
# from the "Certificates" view, which silently omits the private key.
#
# Nothing secret is printed, logged, or written outside a private temp
# directory that is deleted on exit. The .p12 passphrase is generated
# here and stored straight into GitHub; you never need to know it.

set -uo pipefail

REPO="${VK_REPO:-AES256Afro/VideoKidnapper}"
# Overridable so the setup path can be exercised against a throwaway
# keychain in tests without touching the real login keychain.
KEYCHAIN="${VK_KEYCHAIN:-login.keychain-db}"
DRY_RUN=0
P12_INPUT=""

while [ "$#" -gt 0 ]; do
    case "$1" in
        --dry-run)
            DRY_RUN=1
            ;;
        --p12)
            shift
            if [ "$#" -eq 0 ]; then
                echo "error: --p12 requires a path" >&2
                exit 2
            fi
            P12_INPUT="$1"
            ;;
        -h|--help)
            cat <<'EOF'
usage: setup-macos-signing.sh [--dry-run] [--p12 FILE]

  --dry-run   validate everything without writing GitHub secrets
  --p12 FILE  use one existing Developer ID .p12 instead of exporting
              every identity from the login keychain
EOF
            exit 0
            ;;
        *)
            echo "error: unknown option: $1" >&2
            exit 2
            ;;
    esac
    shift
done

G='\033[0;32m'; R='\033[0;31m'; Y='\033[0;33m'; B='\033[0;36m'; D='\033[2m'; O='\033[0m'
ok()   { printf "  ${G}✓${O} %s\n" "$1"; }
bad()  { printf "  ${R}✗${O} %s\n" "$1"; }
warn() { printf "  ${Y}!${O} %s\n" "$1"; }
info() { printf "    ${D}%s${O}\n" "$1"; }
step() { printf "\n${B}%s${O}\n" "$1"; }

WORK=""
cleanup() { [ -n "$WORK" ] && rm -rf "$WORK"; }
trap cleanup EXIT INT TERM

printf "\n${B}macOS signing setup${O} — %s\n" "$REPO"
[ "$DRY_RUN" = "1" ] && warn "dry run: no secrets will be written"

# ---------------------------------------------------------------- 1. tooling
step "1. Checking tools"
for tool in gh security openssl xcrun; do
    command -v "$tool" >/dev/null 2>&1 || { bad "$tool not found"; exit 1; }
done
ok "gh, security, openssl, xcrun present"

if ! gh auth status >/dev/null 2>&1; then
    bad "GitHub CLI is not logged in"
    info "run:  gh auth login"
    exit 1
fi
ok "GitHub CLI authenticated"

if ! gh repo view "$REPO" >/dev/null 2>&1; then
    bad "cannot reach $REPO (wrong repo, or no access)"
    exit 1
fi
ok "can reach $REPO"

# ------------------------------------------------------------ 2. certificate
step "2. Finding your Developer ID certificate"
IDENTITIES="$(security find-identity -v -p codesigning "$KEYCHAIN" 2>/dev/null | grep 'Developer ID Application' || true)"
COUNT="$(printf '%s' "$IDENTITIES" | grep -c 'Developer ID Application' || true)"

if [ "${COUNT:-0}" -eq 0 ]; then
    bad "no 'Developer ID Application' certificate in your keychain"
    echo
    info "You have created it on the portal but not installed it yet:"
    info "  1. Open https://developer.apple.com/account/resources/certificates/list"
    info "  2. Click your Developer ID Application certificate → Download"
    info "  3. Double-click the downloaded .cer (it lands in the login keychain)"
    info "  4. Re-run this script"
    echo
    printf "  Open the certificates page now? [y/N] "
    read -r answer
    case "$answer" in [Yy]*) open "https://developer.apple.com/account/resources/certificates/list" ;; esac
    exit 1
fi

if [ "$COUNT" -gt 1 ]; then
    warn "$COUNT Developer ID Application certificates found"
    printf '%s\n' "$IDENTITIES" | sed -E 's/^ +/    /; s/[0-9A-F]{40}/<hash>/'
    info "This script exports every identity in the login keychain, which"
    info "would upload more private keys than the build needs. Remove the"
    info "ones you do not use, or export a single .p12 by hand and follow"
    info "packaging/macos/README.md."
    exit 1
fi

IDENTITY="$(printf '%s' "$IDENTITIES" | sed -E 's/.*"(.*)".*/\1/')"
TEAM_ID="$(printf '%s' "$IDENTITY" | sed -E 's/.*\(([A-Z0-9]{10})\)$/\1/')"
ok "found: $IDENTITY"
if [ -z "$TEAM_ID" ] || [ "$TEAM_ID" = "$IDENTITY" ]; then
    bad "could not read a Team ID out of the certificate name"
    exit 1
fi
ok "Team ID: $TEAM_ID"

# --------------------------------------------------------------- 3. export
step "3. Exporting the certificate and its private key"
WORK="$(mktemp -d)"
chmod 700 "$WORK"
P12="$WORK/DeveloperID.p12"
if [ -n "$P12_INPUT" ]; then
    if [ ! -f "$P12_INPUT" ]; then
        bad "no such .p12: $P12_INPUT"
        exit 1
    fi
    cp "$P12_INPUT" "$P12"
    chmod 600 "$P12"
    printf "  .p12 export password (hidden): "
    read -rs P12_PASSWORD
    echo
    if [ -z "$P12_PASSWORD" ]; then
        bad "a .p12 export password is required"
        exit 1
    fi
    ok "using the provided .p12 (the original will not be modified)"
else
    P12_PASSWORD="$(openssl rand -base64 24)"
    info "macOS will ask permission to export the private key. This is the"
    info "keychain prompt, and it is expected. Choose Allow."
    echo
    if ! security export -k "$KEYCHAIN" -t identities -f pkcs12 \
            -P "$P12_PASSWORD" -o "$P12" >/dev/null 2>&1; then
        if ! security export -t identities -f pkcs12 \
                -P "$P12_PASSWORD" -o "$P12" >/dev/null 2>&1; then
            bad "export failed (did you deny the keychain prompt?)"
            info "You can export by hand instead: see packaging/macos/README.md"
            exit 1
        fi
    fi
fi
[ -s "$P12" ] || { bad "export produced an empty file"; exit 1; }
ok "staged ($(wc -c < "$P12" | tr -d ' ') bytes)"

# --------------------------------------------------------------- 4. validate
step "4. Checking the export is usable"
DUMP="$(printf '%s\n' "$P12_PASSWORD" | openssl pkcs12 -in "$P12" -nodes -passin stdin 2>/dev/null)"
[ -z "$DUMP" ] && DUMP="$(printf '%s\n' "$P12_PASSWORD" | openssl pkcs12 -in "$P12" -nodes -legacy -passin stdin 2>/dev/null)"
if [ -z "$DUMP" ]; then bad "cannot read the .p12 back"; exit 1; fi
ok "readable"

if printf '%s' "$DUMP" | grep -q -- "-----BEGIN.*PRIVATE KEY-----"; then
    ok "private key present"
else
    bad "no private key — this certificate cannot sign anything"
    info "The key is missing from this Mac. Reissue the certificate from"
    info "the same machine that made the signing request."
    exit 1
fi

CERT_COUNT="$(printf '%s' "$DUMP" | grep -c -- "-----BEGIN CERTIFICATE-----" || true)"
KEY_COUNT="$(printf '%s' "$DUMP" | grep -c -- "-----BEGIN.*PRIVATE KEY-----" || true)"
if [ "${KEY_COUNT:-0}" -gt 1 ]; then
    bad "$KEY_COUNT private keys in the export: more than the build needs"
    info "(leaf + intermediates is normal for certificates; extra KEYS are not)"
    info "Nothing was uploaded. Export only the Developer ID Application"
    info "identity from Keychain Access → login → My Certificates, then"
    info "follow packaging/macos/README.md."
    exit 1
fi
info "$CERT_COUNT certificate(s), $KEY_COUNT private key(s)"

EXPORTED_CERT="$(printf '%s' "$DUMP" | openssl x509 2>/dev/null)"
EXPORTED_SUBJECT="$(printf '%s' "$EXPORTED_CERT" | openssl x509 -noout -subject -nameopt multiline 2>/dev/null)"
EXPORTED_CN="$(printf '%s' "$EXPORTED_SUBJECT" | awk -F' = ' '/commonName/{print $2}')"
EXPORTED_TEAM_ID="$(printf '%s' "$EXPORTED_SUBJECT" | awk -F' = ' '/organizationalUnitName/{print $2}')"
case "$EXPORTED_CN" in
    "Developer ID Application:"*) ok "certificate type: Developer ID Application" ;;
    *)
        bad "export resolved to the wrong certificate: ${EXPORTED_CN:-<none>}"
        info "Nothing was uploaded. Export only the Developer ID Application"
        info "identity from Keychain Access → login → My Certificates."
        exit 1
        ;;
esac
if [ "$EXPORTED_TEAM_ID" != "$TEAM_ID" ]; then
    bad "exported certificate Team ID does not match $TEAM_ID"
    info "Nothing was uploaded."
    exit 1
fi
ok "exported Team ID matches: $TEAM_ID"

if printf '%s' "$DUMP" | openssl x509 -noout -checkend 0 >/dev/null 2>&1; then
    ok "valid until $(printf '%s' "$DUMP" | openssl x509 -noout -enddate 2>/dev/null | cut -d= -f2)"
else
    bad "certificate has expired"
    exit 1
fi

# ------------------------------------------------- 5. notarization credentials
step "5. Apple ID for notarization"
info "notarytool needs an app-specific password, NOT your Apple ID password."
info "Make one at https://account.apple.com → Sign-In and Security."
echo
printf "  Apple ID email: "
read -r APPLE_ID
if [ -z "$APPLE_ID" ]; then bad "an Apple ID is required"; exit 1; fi
printf "  App-specific password (hidden): "
read -rs NOTARY_PASSWORD
echo
if [ -z "$NOTARY_PASSWORD" ]; then bad "an app-specific password is required"; exit 1; fi

step "6. Verifying those credentials with Apple"
info "asking notarytool for your submission history — nothing is uploaded"
if xcrun notarytool history --apple-id "$APPLE_ID" --team-id "$TEAM_ID" \
       --password "$NOTARY_PASSWORD" >/dev/null 2>"$WORK/notary.err"; then
    ok "Apple accepted the credentials"
else
    bad "Apple rejected the credentials"
    sed -E 's/^/    /' "$WORK/notary.err" | head -6
    info "A 401 means the app-specific password or Team ID is wrong."
    info "Nothing was saved. Fix it and re-run."
    exit 1
fi

# ------------------------------------------------------------- 7. store them
step "7. Storing the secrets in $REPO"
if [ "$DRY_RUN" = "1" ]; then
    warn "dry run — would set:"
    for name in MACOS_CERT_P12_BASE64 MACOS_CERT_PASSWORD MACOS_NOTARY_APPLE_ID \
                MACOS_NOTARY_TEAM_ID MACOS_NOTARY_PASSWORD; do
        info "$name"
    done
else
    set_secret() {
        if printf '%s' "$2" | gh secret set "$1" --repo "$REPO" >/dev/null 2>&1; then
            ok "$1"
        else
            bad "failed to set $1"; exit 1
        fi
    }
    set_secret MACOS_CERT_P12_BASE64  "$(base64 < "$P12")"
    set_secret MACOS_CERT_PASSWORD    "$P12_PASSWORD"
    set_secret MACOS_NOTARY_APPLE_ID  "$APPLE_ID"
    set_secret MACOS_NOTARY_TEAM_ID   "$TEAM_ID"
    set_secret MACOS_NOTARY_PASSWORD  "$NOTARY_PASSWORD"
fi

unset NOTARY_PASSWORD P12_PASSWORD

step "Done"
if [ "$DRY_RUN" = "1" ]; then
    info "Re-run without --dry-run to write the secrets."
else
    ok "All five secrets are set. The temporary .p12 copy has been deleted."
    [ -n "$P12_INPUT" ] && info "The original remains at: $P12_INPUT"
    echo
    info "Next: build a signed DMG without cutting a release —"
    info "  gh workflow run macos.yml --repo $REPO"
    info "Then check the 'Verify the shipped .dmg' step says: accepted"
fi
echo
