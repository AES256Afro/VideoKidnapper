# Repository setup

A short checklist for the maintainer — things to configure on GitHub itself before going fully public. Do these once from the repository's **Settings** page.

## Metadata

- **Description.** Something like:
  > Desktop tool for trimming videos and creating GIFs with text overlays. Downloads from YouTube, Instagram, Bluesky, X, Reddit, and Facebook.
- **Topics** (up to 10 searchable tags):
  `video` · `gif` · `ffmpeg` · `yt-dlp` · `tkinter` · `customtkinter` · `python` · `video-editor` · `screen-recorder` · `desktop-app`
- **Website / homepage**: either point at a project page, a demo video, or leave blank.

## Branch protection

Apply to `main` from **Settings → Branches → Add branch protection rule**:

- ☑ Require a pull request before merging
  - ☑ Require approvals (1)
  - ☑ Dismiss stale approvals when new commits are pushed
- ☑ Require status checks to pass before merging
  - Pick every job from the CI workflow: **Ruff**, **Tests on ubuntu-latest / Python 3.11**, **… / 3.12**, **Tests on windows-latest / Python 3.11**, **… / 3.12**
  - ☑ Require branches to be up to date before merging
- ☑ Require linear history
- ☑ Do not allow bypassing the above settings

## Security

- **Settings → Code security and analysis**:
  - ☑ Dependency graph (usually on by default for public repos)
  - ☑ Dependabot alerts
  - ☑ Dependabot security updates
  - ☑ Secret scanning + push protection
- The `.github/dependabot.yml` in this repo handles version-bump PRs on its own schedule.

## Issues & community

- **Settings → General → Features**:
  - ☑ Issues
  - ☑ Discussions (optional but nice for "how do I…" questions)
- Issue templates live in `.github/ISSUE_TEMPLATE/`; the bug-report form requires Debug-tab output, which makes triage much faster.

## Releases

When you're ready for `v1.0.0`:

```bash
git tag -a v1.0.0 -m "Initial public release"
git push origin v1.0.0
```

Then go to **Releases → Draft a new release**, select the tag, let GitHub auto-generate release notes from the commit log, and publish.

## Automated checks that already run

- **CI** (`.github/workflows/ci.yml`) — runs pytest on Ubuntu + Windows across two Python versions, plus a Ruff lint job, on every push to `main` and every PR.
- **Dependabot** — weekly pip PRs (grouped by minor/patch), monthly GitHub Actions PRs.
