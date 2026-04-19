# Privacy Policy

*Last updated: 2026-04-19*

VideoKidnapper is a desktop application that runs entirely on the user's
own machine. **It does not collect, store, or transmit any personal
data, usage analytics, telemetry, or crash reports to the project
maintainer or to any third party.**

## What stays local

Every piece of data the app touches stays on the user's computer:

- Videos you open, trim, or export.
- URLs you paste into the URL tab and the corresponding downloaded
  files (which land wherever the user configures — defaults to the
  system Downloads folder).
- Text captions, image overlays, crop rectangles, and every other
  edit you make inside the app.
- Your settings file at `~/.videokidnapper_settings.json` (preferred
  output folder, chosen theme, recent-export history, etc.).
- The cookie data the app reads from your browser to download
  private / age-gated videos you have access to. This is read locally
  by `yt-dlp`; it is never transmitted anywhere except to the video
  host you are downloading from, using your existing session.

Nothing from the list above leaves your computer at any point.

## Network activity

VideoKidnapper does make outbound network connections, but only to
servers the user has directed it to or to well-known public services
required for a core feature. Specifically:

- **User-initiated downloads.** When you paste a URL and click
  Download, the app (via `yt-dlp`) contacts the host of that URL
  (YouTube, Instagram, Bluesky, X / Twitter, Reddit, Facebook, etc.)
  using your existing session cookies if present. No VideoKidnapper
  server sits in the middle.
- **Update check.** Once per launch, the app queries
  `https://api.github.com/repos/AES256Afro/VideoKidnapper/releases/latest`
  to see whether a newer version exists. This is a public, anonymous
  GitHub API call; no identifying information is sent. The check can
  be disabled from the Setup dialog
  (`auto_update_check` setting → false).
- **Optional AI captions (opt-in, off by default).** If the user
  installs the optional `faster-whisper` extra and clicks
  🗣 Auto-captions, the Whisper model is downloaded from Hugging
  Face the first time it is used, and subsequent runs use the local
  cache. No audio ever leaves your computer — transcription happens
  entirely offline once the model is cached.
- **Optional `github_update` module**. No other network activity
  exists anywhere in the codebase. You can audit this yourself by
  searching the source tree for `urllib`, `requests`, `http`, or
  `socket`.

## Third-party software

The app bundles (or optionally depends on) the following open-source
projects, each with its own upstream license and privacy posture:

- `ffmpeg` — external binary prerequisite, handles all
  encoding / decoding.
- `yt-dlp` — downloads from video hosts. Network calls go directly
  to those hosts.
- `customtkinter`, `tkinterdnd2`, `Pillow`, `imageio-ffmpeg`,
  `sounddevice`, `faster-whisper` (optional) — client-side libraries,
  none of which phone home in the way VideoKidnapper uses them.

## No account system, no logins, no cloud

VideoKidnapper does not offer a user account, does not require
registration, does not sync data to any cloud service, and does not
operate any backend server that processes user data.

## Contact

Questions or concerns about this policy can be filed as a GitHub
issue at https://github.com/AES256Afro/VideoKidnapper/issues or
raised on a pull request.

## Changes to this policy

If the data-handling posture of the app ever changes (e.g. if a
future release adds opt-in crash reporting, or a remote model
inference feature), this document will be updated in the same
commit that introduces the change, and a `### Changed` entry in
`CHANGELOG.md` will call it out explicitly.
