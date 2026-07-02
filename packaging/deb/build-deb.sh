#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
#
# Assemble videokidnapper_<version>_amd64.deb from the PyInstaller
# one-dir bundle. Run from the repo root (on Linux):
#
#   packaging/deb/build-deb.sh <version> <bundle-dir> <out.deb>
#
# e.g. packaging/deb/build-deb.sh 1.4.0 dist/VideoKidnapper videokidnapper_1.4.0_amd64.deb
#
# Layout: the bundle lands in /opt/videokidnapper with a /usr/bin
# symlink, plus the .desktop entry and hicolor icon. FFmpeg is NOT
# bundled — `Depends: ffmpeg` lets apt install the distro's copy
# (unlike the AppImage, apt can resolve dependencies).
set -euo pipefail

VERSION="$1"
BUNDLE="$2"
OUT="$3"

ROOT=$(mktemp -d)
trap 'rm -rf "$ROOT"' EXIT

mkdir -p \
  "$ROOT/DEBIAN" \
  "$ROOT/opt/videokidnapper" \
  "$ROOT/usr/bin" \
  "$ROOT/usr/share/applications" \
  "$ROOT/usr/share/icons/hicolor/512x512/apps" \
  "$ROOT/usr/share/doc/videokidnapper"

cp -r "$BUNDLE"/. "$ROOT/opt/videokidnapper/"
ln -s /opt/videokidnapper/VideoKidnapper "$ROOT/usr/bin/videokidnapper"

# Reuse the AppImage desktop entry; only the Exec target differs.
sed 's|^Exec=VideoKidnapper|Exec=videokidnapper|' \
  packaging/appimage/videokidnapper.desktop \
  > "$ROOT/usr/share/applications/videokidnapper.desktop"
cp assets/branding/logo-512.png \
  "$ROOT/usr/share/icons/hicolor/512x512/apps/videokidnapper.png"
cp LICENSE "$ROOT/usr/share/doc/videokidnapper/copyright"

INSTALLED_SIZE=$(du -sk --exclude=DEBIAN "$ROOT" | cut -f1)

cat > "$ROOT/DEBIAN/control" <<EOF
Package: videokidnapper
Version: $VERSION
Architecture: amd64
Maintainer: Christopher Courtney <sinth.tek@gmail.com>
Installed-Size: $INSTALLED_SIZE
Depends: ffmpeg, libc6 (>= 2.35)
Recommends: xclip
Section: video
Priority: optional
Homepage: https://github.com/AES256Afro/VideoKidnapper
Description: Trim, caption, and export video clips and GIFs
 Dark-themed desktop tool for trimming videos, downloading clips from
 the open web, and exporting polished GIFs or MP4s with text and image
 overlays. Ships its own Python runtime (PyInstaller bundle); FFmpeg
 comes from the distro via the ffmpeg dependency.
EOF

dpkg-deb --build --root-owner-group "$ROOT" "$OUT"
dpkg-deb --info "$OUT"
