# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
#
# Homebrew formula for VideoKidnapper.
#
# This formula lives in a personal tap rather than homebrew-core (the app
# is niche GUI software; homebrew-core prefers utilities). Publish by
# copying this file into the tap repo `AES256Afro/homebrew-videokidnapper`
# in a `Formula/` directory.
#
# POST-RELEASE CHECKLIST (fill this in after each tag push):
#
#   1. Wait for the PyPI release.yml workflow to finish (PR #11).
#   2. Grab the sdist SHA256 from PyPI:
#         curl -sL https://pypi.org/pypi/videokidnapper/VERSION/json \
#           | jq -r '.urls[] | select(.packagetype=="sdist") | .digests.sha256'
#   3. Update `url`, `version`, and `sha256` below.
#   4. `brew audit --strict --new-formula videokidnapper.rb`
#   5. Copy the file to the tap repo, commit, push.
#
# After the tap is pushed, users install with:
#     brew tap AES256Afro/videokidnapper
#     brew install videokidnapper

class Videokidnapper < Formula
  include Language::Python::Virtualenv

  desc "Dark-themed desktop tool for trimming videos and exporting GIFs or MP4s"
  homepage "https://github.com/AES256Afro/VideoKidnapper"
  url "https://files.pythonhosted.org/packages/source/v/videokidnapper/videokidnapper-1.2.0.tar.gz"
  sha256 "REPLACE_WITH_SDIST_SHA256_AFTER_RELEASE"
  license "Apache-2.0"
  head "https://github.com/AES256Afro/VideoKidnapper.git", branch: "main"

  depends_on "python@3.12"
  depends_on "ffmpeg"          # FFmpeg isn't PyPI-installable; brew handles it
  depends_on "python-tk@3.12"  # Tk support for customtkinter

  # Resource list is intentionally minimal — only the hard-pinned deps.
  # Everything else is pulled transitively by pip inside the venv.
  resource "customtkinter" do
    url "https://files.pythonhosted.org/packages/source/c/customtkinter/customtkinter-5.2.2.tar.gz"
    sha256 "REPLACE_WITH_CUSTOMTKINTER_SDIST_SHA256"
  end

  resource "Pillow" do
    url "https://files.pythonhosted.org/packages/source/p/pillow/pillow-11.0.0.tar.gz"
    sha256 "REPLACE_WITH_PILLOW_SDIST_SHA256"
  end

  resource "mss" do
    url "https://files.pythonhosted.org/packages/source/m/mss/mss-10.0.0.tar.gz"
    sha256 "REPLACE_WITH_MSS_SDIST_SHA256"
  end

  resource "yt-dlp" do
    url "https://files.pythonhosted.org/packages/source/y/yt-dlp/yt_dlp-2025.1.1.tar.gz"
    sha256 "REPLACE_WITH_YT_DLP_SDIST_SHA256"
  end

  def install
    virtualenv_install_with_resources
  end

  test do
    # Smoke test — argparse short-circuits before Tk imports, so --version
    # runs without a display on CI / headless Homebrew installs.
    assert_match "videokidnapper", shell_output("#{bin}/videokidnapper --version")
  end
end
