# Release playbook

How to cut a new version. Written for maintainers.

The project ships through **four distribution channels**, each gated on the same `vX.Y.Z` git tag:

| Channel | Trigger | Artifact | Who maintains |
|---|---|---|---|
| **PyPI** | `release.yml` on tag push | sdist + wheel | automated |
| **GitHub Release** | `release.yml` + `installer.yml` on tag push | sdist, wheel, `VideoKidnapper.exe` | automated |
| **Homebrew tap** | manual — post-release | `AES256Afro/homebrew-videokidnapper` formula | manual |
| **Winget** | manual — PR to `microsoft/winget-pkgs` | manifest files under `manifests/a/AES256Afro/VideoKidnapper/X.Y.Z/` | manual (bot-reviewed) |

---

## One-time setup (do this once per maintainer machine)

### PyPI Trusted Publishing

Required before the first automated release works. No API token needs to land in GitHub secrets — OIDC handles it.

1. Visit https://pypi.org/manage/account/publishing/
2. **Add a pending publisher** with:
   - Owner: `AES256Afro`
   - Repo: `VideoKidnapper`
   - Workflow: `release.yml`
   - Environment: `pypi`
3. First successful tag push promotes the pending publisher to permanent.

### Homebrew tap

Create the empty tap repo once: **`AES256Afro/homebrew-videokidnapper`** on GitHub. That's it — per-release updates go into a `Formula/` directory there, copied from `packaging/homebrew/`.

---

## Per-release checklist

Pick a new version per SemVer — usually you'll want a minor bump for feature batches, patch for fixes.

### 1. Bump the version

```bash
# Open videokidnapper/__init__.py and update __version__
vim videokidnapper/__init__.py

# Move the [Unreleased] CHANGELOG header to [X.Y.Z] — YYYY-MM-DD
# Add a new link target at the bottom
vim CHANGELOG.md
```

The CI tripwire in `release.yml` compares the tag name to `__version__` and fails if they disagree — this prevents a mis-tagged release from shipping.

Commit and merge to `main` via a PR.

### 2. Tag and push

```bash
git checkout main
git pull
git tag v1.2.0
git push --tags
```

### 3. Watch the workflows

Two workflows fire in parallel:

- **`release.yml`** → builds sdist + wheel, publishes to PyPI, attaches to GitHub Release
- **`installer.yml`** → builds `VideoKidnapper.exe` on Windows, attaches to GitHub Release

Both are independent — a failure in one doesn't stop the other. Check `Actions` tab for progress.

### 4. Update Homebrew tap (~5 min)

Once PyPI has the sdist:

```bash
# Grab the sdist SHA256 from PyPI
curl -sL https://pypi.org/pypi/videokidnapper/1.2.0/json \
  | jq -r '.urls[] | select(.packagetype=="sdist") | .digests.sha256'

# Update the formula
vim packaging/homebrew/videokidnapper.rb
# Replace: version string, url, sha256
# Refresh resource blocks with:  brew update-python-resources videokidnapper

# Copy to the tap
cp packaging/homebrew/videokidnapper.rb \
   ../homebrew-videokidnapper/Formula/videokidnapper.rb
cd ../homebrew-videokidnapper
git commit -am "videokidnapper 1.2.0" && git push
```

See `packaging/homebrew/README.md` for the longer version.

### 5. Submit winget manifests (~10 min + bot review time)

Once the GitHub Release has `VideoKidnapper.exe` uploaded:

```powershell
# Grab the SHA256
(Get-FileHash -Algorithm SHA256 VideoKidnapper.exe).Hash
```

Update `packaging/winget/manifests/1.2.0/*.yaml` with the real hash + version. Then submit a PR to [`microsoft/winget-pkgs`](https://github.com/microsoft/winget-pkgs) copying the three YAML files to:

```
manifests/a/AES256Afro/VideoKidnapper/1.2.0/
```

Microsoft's validation bot runs automatically and usually merges within 24 hours.

See `packaging/winget/README.md` for the longer version.

---

## If something goes wrong

- **Tag vs version mismatch** → `release.yml` fails before publish. Delete the tag (`git tag -d v1.2.0 && git push --delete origin v1.2.0`), bump `__version__` correctly, retag.
- **PyPI publish fails** → Trusted Publishing setup probably isn't done yet (see "One-time setup"). Re-run the workflow after configuring.
- **PyInstaller build fails on Windows** → hit the **`workflow_dispatch`** trigger on `installer.yml` once you've fixed the issue; rebuilds for the existing tag without needing a re-tag.
- **Homebrew audit complains** → run `brew audit --strict --new-formula` locally first. Common issues: outdated `resource` URLs, missing `license` field, wrong `depends_on` ordering.
- **Winget bot rejects** → the bot's feedback is usually actionable. Most common: wrong SHA256, invalid YAML schema version, or a `Moniker:` collision.

---

## Rollback

PyPI doesn't allow re-uploading a version, and tags are immutable. If a release is bad:

1. **Yank from PyPI** (not delete — yanking hides it from `pip install videokidnapper` without breaking reproducible installs of projects that pinned it): https://pypi.org/manage/project/videokidnapper/
2. **Edit the GitHub Release** to note the issue prominently.
3. **Cut a patch release** (`1.2.1`) with the fix. Don't try to reuse the bad version.
