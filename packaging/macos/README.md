# macOS build

Builds **`VideoKidnapper-X.Y.Z-macos-arm64.dmg`** (Apple Silicon) and
**`-x86_64.dmg`** (Intel) — a standalone `.app`, no Python required. FFmpeg
is bundled.

## How it's built

`.github/workflows/macos.yml` on tag push, one job per arch (macos-14 =
Apple Silicon, macos-15-intel = Intel — PyInstaller can't cross-compile a
`.app`, so each architecture builds on its own runner):

1. `packaging/videokidnapper-macos.spec` → `dist/VideoKidnapper.app` (PyInstaller `BUNDLE`, `.icns` icon).
2. Static **ffmpeg/ffprobe** (per-arch: [evermeet.cx](https://evermeet.cx/ffmpeg/) is Intel-only, so Apple Silicon uses [eugeneware/ffmpeg-static](https://github.com/eugeneware/ffmpeg-static)) drop into `Contents/Resources/assets/ffmpeg/bin` — a `.app` has no reliable PATH, so the app's resolver (`videokidnapper/utils/ffmpeg_check.py`, frozen branch) looks next to the executable / in Resources.
3. `create-dmg` wraps it with an Applications drop-link (falls back to `hdiutil` if unavailable).

## Signing and notarization

The workflow has two modes, chosen automatically by whether the signing
secrets exist. **No secrets = the build still works**, so forks and PRs
from forks are unaffected.

| | Without secrets | With secrets |
|---|---|---|
| Signature | ad-hoc | Developer ID Application |
| Hardened runtime | no | yes (`--options runtime`) |
| Notarized + stapled | no | yes |
| Gatekeeper verdict | `rejected` | `accepted` |
| User's first launch | one trip through **Open Anyway** | opens normally |

The ad-hoc signature is *not* optional even in the free mode: the arm64
kernel refuses to exec an improperly signed binary at all. Any step that
writes into the `.app` must be followed by a re-sign — see the workflow's
"Re-sign the bundle" step and the 1.8.0 entry in `CHANGELOG.md` for what
happens otherwise.

### One-time setup

**The short way — one command:**

```bash
./scripts/setup-macos-signing.sh
```

It finds your Developer ID certificate, exports the `.p12` for you
(generating and storing its passphrase, so there is nothing to invent
or remember), verifies the export actually carries the private key,
checks your notarization credentials against Apple before saving
anything, and writes all five repository secrets. Add `--dry-run` to
see what it would do first.

Nothing secret is printed or written outside a private temp directory
that is deleted on exit, and the script refuses to continue rather than
storing credentials Apple has already rejected.

The manual route below is the fallback — worth reading if the script
stops on something, or if you would rather do it by hand.

### One-time setup, by hand

**1. Install the certificate.** Download the *Developer ID Application*
`.cer` from [certificates](https://developer.apple.com/account/resources/certificates/list)
and double-click it. It lands in the **login** keychain.

**2. Export it as `.p12` — with the private key.** In *Keychain Access*
→ **login** → *My Certificates* (not *Certificates* — that view hides the
key), find `Developer ID Application: <name> (<TEAMID>)`, expand the
triangle to confirm a private key is nested under it, then right-click
the **certificate** → *Export*. Choose *Personal Information Exchange
(.p12)* and set a strong password.

> Exporting without the private key is the single most common mistake
> here. The workflow catches it: it resolves the identity from the
> keychain after import and fails with a clear message rather than
> producing an unsigned build.

**3. Create an app-specific password** at
[account.apple.com](https://account.apple.com) → *Sign-In and Security*
→ *App-Specific Passwords*. Your normal Apple ID password will not work
with `notarytool`.

**4. Check the export before uploading it.**

```bash
./scripts/check-macos-signing.sh ~/Desktop/DeveloperID.p12
```

Everything runs locally; nothing is uploaded and the password is read
with a hidden prompt. A good export looks like this:

```
Checking DeveloperID.p12

  .p12 export password:

  ✓ opened the .p12 (password correct)
  ✓ contains a private key
  ✓ certificate type: Developer ID Application
  ✓ valid until Feb  1 12:00:00 2027 GMT
  ✓ Team ID: U7X9DNSQ7Z
      use this for the MACOS_NOTARY_TEAM_ID secret

  Signing identity the build will resolve:
    Developer ID Application: Christopher Courtney (U7X9DNSQ7Z)

  Ready to upload.
```

The failure you are most likely to hit — exporting from the wrong
Keychain Access view:

```
  ✓ opened the .p12 (password correct)
  ✗ NO PRIVATE KEY — this file cannot sign anything
      In Keychain Access choose the 'My Certificates' category, not
      'Certificates'. Expand the triangle next to the certificate; if
      no key is nested under it, the key is missing from this Mac and
      you must reissue the certificate.
```

Such a file imports into CI without error and then fails much later
with a confusing `codesign` message, which is why it is worth catching
here. The script exits non-zero on any hard failure.

**5. Add the repository secrets.** Run these yourself — never paste
secret values into a chat, an issue, or a commit:

```bash
base64 -i ~/Desktop/DeveloperID.p12 | gh secret set MACOS_CERT_P12_BASE64
gh secret set MACOS_CERT_PASSWORD       # the .p12 export password
gh secret set MACOS_NOTARY_APPLE_ID     # your Apple ID email
gh secret set MACOS_NOTARY_TEAM_ID      # 10-char Team ID, e.g. U7X9DNSQ7Z
gh secret set MACOS_NOTARY_PASSWORD     # the app-specific password
```

Each `gh secret set` without a value prompts on stdin, so the secret
never lands in your shell history. Confirm they registered — this
prints names and timestamps only, never values:

```bash
gh secret list
```

```
MACOS_CERT_P12_BASE64    Updated 2026-08-06
MACOS_CERT_PASSWORD      Updated 2026-08-06
MACOS_NOTARY_APPLE_ID    Updated 2026-08-06
MACOS_NOTARY_PASSWORD    Updated 2026-08-06
MACOS_NOTARY_TEAM_ID     Updated 2026-08-06
```

**6. Verify the credentials work** before relying on a release build.
This authenticates against Apple without submitting anything:

```bash
xcrun notarytool history \
  --apple-id "you@example.com" \
  --team-id "U7X9DNSQ7Z" \
  --password "your-app-specific-password"
```

Success prints a (possibly empty) submission history. `HTTP status code:
401` means the app-specific password or Team ID is wrong — fix that now
rather than discovering it during a release.

Then delete the local `.p12` and keep a backup somewhere secure. A
Developer ID certificate cannot be re-downloaded with its private key —
only revoked and reissued.

### Trying it end to end before tagging a release

`macos.yml` has a `workflow_dispatch` trigger, so you can exercise the
whole signed path without cutting a release. Leave the `tag` input
empty and it builds artifacts only:

```bash
gh workflow run macos.yml
gh run watch
```

Then download the artifact and confirm the goal state:

```bash
hdiutil attach VideoKidnapper-*-macos-arm64.dmg
spctl -a -t exec -vvv /Volumes/VideoKidnapper/VideoKidnapper.app
```

```
/Volumes/VideoKidnapper/VideoKidnapper.app: accepted
source=Notarized Developer ID
```

`accepted` + `Notarized Developer ID` means users get a clean first
launch. `rejected` means the build fell back to ad-hoc — check the
"Detect signing configuration" step in the run log, which prints
whether it found the secrets.

| Secret | Purpose |
|---|---|
| `MACOS_CERT_P12_BASE64` | Developer ID cert + private key |
| `MACOS_CERT_PASSWORD` | password for the above |
| `MACOS_NOTARY_APPLE_ID` | Apple ID for `notarytool` |
| `MACOS_NOTARY_TEAM_ID` | Team ID |
| `MACOS_NOTARY_PASSWORD` | app-specific password |

Signing turns on with `MACOS_CERT_P12_BASE64` alone; notarization also
needs `MACOS_NOTARY_PASSWORD`. Certificates expire after ~5 years and
app-specific passwords break if you change your Apple ID password — in
both cases the build fails loudly rather than silently shipping
unsigned.

### Verifying a release

The workflow already checks the shipped `.dmg` under quarantine and
fails if a notarized build isn't `accepted`. To confirm by hand:

```bash
spctl -a -t exec -vvv /Volumes/VideoKidnapper/VideoKidnapper.app
xcrun stapler validate VideoKidnapper-X.Y.Z-macos-arm64.dmg
```

`accepted` + `source=Notarized Developer ID` is the goal state.

## Licensing note

The bundled FFmpeg is a GPL static build. VideoKidnapper invokes it as a separate process (mere aggregation — the app stays Apache-2.0); the release notes link the source. To avoid GPL entirely, swap in an LGPL macOS build — but confirm it includes libx264, which the encoder fallback and GIF intermediate need.

## Local build (on a Mac)

```bash
pip install -r requirements.txt pyinstaller
python -m PyInstaller packaging/videokidnapper-macos.spec --noconfirm --clean
# then drop ffmpeg/ffprobe into
#   dist/VideoKidnapper.app/Contents/Resources/assets/ffmpeg/bin
open dist/VideoKidnapper.app
```
