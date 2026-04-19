# Homebrew tap — `AES256Afro/homebrew-videokidnapper`

The formula in `videokidnapper.rb` lets macOS + Linux users install the app with `brew`.

## Why a personal tap, not homebrew-core

homebrew-core prefers compiled utilities and libraries. GUI applications — especially Python-based ones with a handful of transitive dependencies — get pushed toward personal taps. That's also the faster path: no maintainer review queue.

## One-time setup (maintainer)

1. Create the tap repo on GitHub: **`AES256Afro/homebrew-videokidnapper`**.
2. Clone it, then `cp packaging/homebrew/videokidnapper.rb ./Formula/videokidnapper.rb` in the tap repo.
3. Commit + push.

After that, users install with:

```bash
brew tap AES256Afro/videokidnapper
brew install videokidnapper
```

## Per-release update

After each tag-push triggers a successful PyPI release:

1. Grab the sdist SHA256 from PyPI:

   ```bash
   curl -sL https://pypi.org/pypi/videokidnapper/1.2.0/json \
     | jq -r '.urls[] | select(.packagetype=="sdist") | .digests.sha256'
   ```

2. Update `url`, `version`, and `sha256` in the formula to match the release.
3. Refresh the `resource` blocks for any deps that bumped — Homebrew's `brew update-python-resources videokidnapper` automates this.
4. `brew audit --strict --new-formula videokidnapper.rb` to catch formatting issues.
5. Commit to the tap, push — users' `brew upgrade` picks it up.

## Testing locally before publishing

```bash
brew install --build-from-source ./packaging/homebrew/videokidnapper.rb
brew test videokidnapper
brew audit --strict videokidnapper
```

## Known caveats

- **FFmpeg is a hard `depends_on`.** Unlike the pip install, Homebrew handles ffmpeg for us — no in-app Setup dialog needed on Mac.
- **`python-tk@3.12` is required** for customtkinter. macOS's system Python doesn't ship Tk bindings; Homebrew's Python does, but the tk formula is a separate dep.
- **Apple Silicon vs Intel:** the sdist is pure Python, so the same formula serves both. Native resources (Pillow wheels) are picked automatically by pip.
