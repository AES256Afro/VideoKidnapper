# Security policy

## Supported versions

The `main` branch is actively maintained. Older tagged releases only receive security fixes on a best-effort basis.

## Reporting a vulnerability

If you find a vulnerability — especially one affecting:

- **Filter-graph / drawtext injection** via user text, filenames, or URLs
- **Arbitrary command execution** through the admin-terminal opener or screen-record / downloader paths
- **Cookie / credential exposure** in the `Cookies from browser` flow or settings file
- **Path traversal** in file-naming, settings, or export paths

...please do **not** open a public issue. Instead:

1. Open a private report via GitHub's **Security → Report a vulnerability** on the repository.
2. Or email the repository owner directly if you can find a public-facing address.

Please include:
- Affected version (or commit SHA)
- Reproduction steps or a minimal proof-of-concept
- Your assessment of impact

## Handling

- Confirmed reports receive an acknowledgement within 7 days.
- A fix and coordinated disclosure timeline will be agreed with the reporter.
- Credit is given in release notes unless you request anonymity.

## Out of scope

- Issues requiring an attacker already inside your user session (the cookie-export feature is user-initiated; browser cookies are a deliberate, opt-in input)
- Vulnerabilities in our dependencies that are best reported upstream — please report those to `yt-dlp`, `customtkinter`, `Pillow`, `mss`, `tkinterdnd2`, or `FFmpeg` directly.
- Downloading content that violates a platform's terms of service is a policy question, not a security one.

## Hardening tips for users

- Keep `yt-dlp` up to date: `python -m pip install --user --upgrade yt-dlp`. Extractor fixes ship frequently.
- Keep FFmpeg updated via the **⚙ Setup** dialog or your OS package manager.
- Use the **Cookies from browser** option rather than manual cookie files when possible — it avoids leaving cookie exports on disk.
