# Debian / Ubuntu package + APT repository

Builds **`videokidnapper_X.Y.Z_amd64.deb`** and publishes it to the signed APT repo at [`AES256Afro/apt`](https://github.com/AES256Afro/apt) (served via GitHub Pages), so users can:

```bash
# one-time
sudo install -d /etc/apt/keyrings
curl -fsSL https://aes256afro.github.io/apt/videokidnapper.asc | sudo tee /etc/apt/keyrings/videokidnapper.asc > /dev/null
echo "deb [signed-by=/etc/apt/keyrings/videokidnapper.asc] https://aes256afro.github.io/apt stable main" | sudo tee /etc/apt/sources.list.d/videokidnapper.list
sudo apt update

# forever after
sudo apt install videokidnapper     # upgrades arrive via `apt upgrade`
```

## How it works

`appimage.yml`'s build job reuses the PyInstaller one-dir bundle it already makes for the AppImage; `build-deb.sh` wraps it:

- Bundle → `/opt/videokidnapper/`, launcher symlink → `/usr/bin/videokidnapper`
- Desktop entry + hicolor icon (app shows in the launcher menu)
- **`Depends: ffmpeg, libc6 (>= 2.35)`** — unlike the AppImage, apt resolves dependencies, so FFmpeg comes from the distro and is NOT bundled. `Recommends: xclip` for clipboard copy.
- The libc floor comes from the ubuntu-22.04 build runner — same floor as the AppImage.

The `publish-apt` job (tags + manual dispatch with a tag only) then:

1. Imports the GPG signing key (`APT_GPG_PRIVATE_KEY` repo secret; fingerprint `AE75 B3E7 AA43 FDC5 CDF2 AE58 3C3F 0BDB 03B3 3789`)
2. Clones `AES256Afro/apt` over SSH (`APT_REPO_DEPLOY_KEY` secret; write-enabled deploy key)
3. Drops the deb into `pool/main/v/videokidnapper/`, regenerates `dists/stable/` indexes with `apt-ftparchive`, signs `Release` → `Release.gpg` + `InRelease`
4. Commits and pushes; GitHub Pages serves the update within a minute or two

## Why not the official archives or a PPA?

Debian/Ubuntu inclusion needs every Python dep packaged in the archive (`customtkinter` isn't) and freezes versions for years — fatal for a yt-dlp-based app. Launchpad PPA builders have no network, so they can't fetch wheels either. The vendor-repo model (same as Docker/VS Code/Chrome) is the standard answer.

## Key rotation / disaster recovery

The private key backup lives on the maintainer machine at `~/.videokidnapper-secrets/`. If it's ever lost or compromised: generate a new key, replace `videokidnapper.asc` in the apt repo, update the `APT_GPG_PRIVATE_KEY` secret, and users must re-run the one-time key install line.
