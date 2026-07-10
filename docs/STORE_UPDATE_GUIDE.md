# Updating the Microsoft Store listing

Step-by-step for refreshing the VideoKidnapper listing on Partner Center:
the description, the feature list, the screenshots, the logo, and the app
package. All the text to paste lives in `docs/STORE_LISTING.md`; all the
images live in the repo (paths below).

Start at **[partner.microsoft.com/dashboard](https://partner.microsoft.com/dashboard)
→ Apps and games → VideoKidnapper**, then click **Start update** on the
Product release row. That clones the live submission into an editable
draft. Everything below happens inside that draft; nothing goes live
until you click **Submit for certification** at the end.

---

## 1. Description and features

Open **Store listings → English (United States)**.

- **Description** field: paste the block under *"Description (Store field)"* in `docs/STORE_LISTING.md`.
- **Product features** field: paste the lines under *"Product features"* in `docs/STORE_LISTING.md`, one feature per line (Partner Center shows them as a bulleted list). Up to 20 lines.
- **Short description** (if present): the one-liner under *"Short description"* in the same doc.

These are already written feature-first with no em dashes. Copy verbatim.

## 2. Screenshots

Still in **Store listings → English → Screenshots**.

1. Remove the existing screenshots.
2. Upload the files from `assets/store/` (each is exactly 1920×1080, the size the Store requires):
   - `01-studio-1920x1080.png` — the editor with a clip, caption, and queued cut
   - `02-download-1920x1080.png` — the download bar + batch queue
   - `03-start-1920x1080.png` — the empty/start state
   - `04-history-1920x1080.png` — export history
   - `05-setup-1920x1080.png` — the setup screen
   - `06-motion-1920x1080.png` — motion-tracked caption following a subject across three frames
3. Order them 01 → 06 (drag to reorder). The first is the hero shot.

To regenerate these after a UI change: `python scripts/capture_screenshots.py` (writes `assets/screenshots/*.png`), then the store-resize step in that script's notes produces `assets/store/*`.

## 3. Logo / Store images

Under **Store listings → Store logos** (and the package tiles). The mark
is the balaclava on the dark brand tile, one consistent look everywhere:

- **1:1 box art** (1080×1080 / 2160×2160): `assets/branding/store-boxart-1080x1080.png` / `-2160x2160.png`
- **9:16 poster art** (720×1080 / 1440×2160): `assets/branding/store-poster-720x1080.png` / `-1440x2160.png`
- **Tile overrides** (300 / 150 / 71): `assets/branding/store-tile-300x300.png`, etc. — optional; the package already carries matching tiles in `packaging/msix/Assets/`.

You usually don't need to touch these unless the mark changed. They're regenerated from `assets/branding/logo.svg` by the asset script (see the branding README).

## 4. App package (new version)

Under **Packages**:

1. A new build is produced by CI on every version tag — grab `VideoKidnapper.msix` from the **MSIX (Microsoft Store)** workflow run's artifacts (Actions → that run → Artifacts → `VideoKidnapper-msix-store`), or ask for it.
2. Remove the old package, drag the new `.msix` in, wait for **"Validated."**
3. The package version must be higher than the live one (e.g. `1.6.0.0` > `1.5.1.0`). CI stamps this from the git tag automatically.

If only the listing text/screenshots changed and the app itself didn't, you can keep the existing package and skip this step.

## 5. Submit

1. Fill **What's new in this version** from `docs/STORE_LISTING.md` → *"What's new in this version"*.
2. Fill **Notes for certification** (the free-text box for the review team) with the block in *"Certification notes"* below. **Always include this** — it heads off the offline/functionality rejection described there.
3. Click **Submit for certification**. Certification for updates is usually a few hours. It auto-publishes on pass; existing users update automatically.

---

## Certification notes

Paste this into **Notes for certification** on every submission. It exists
because a June 2026 submission was rejected under **Store policy 10.1.2.10
(Functionality)** with *"Unusable Feature: Working offline"* — the tester
disconnected the network, tried to download a video, and saw it fail.
Downloading is inherently online, so the fix (shipped in 1.7.4) was to
make the offline state clear and graceful rather than a cryptic error; the
note tells the reviewer that up front so they don't file the same finding.

```
Testing notes:

- VideoKidnapper's download feature fetches video from online services (YouTube, Reddit, Instagram, etc.), so it requires an active internet connection by design. This is the app's core purpose and is an inherently online operation.

- When offline, the app does NOT present a broken feature. Attempting a download shows a clear, plain message ("No internet connection. Connect to the internet to download videos. You can still open a local file to trim, caption, and export.") and does not hang or show a cryptic error.

- All editing works fully offline. Use Open Video File (or drag a file in, or Record Screen) to load a local video, then trim, add captions and overlays, and export a GIF or MP4 with no connection.

To verify offline behavior: launch the app, open any local video file, trim it, add a caption, and export. All of this succeeds with the network disconnected. The only feature that needs a connection is downloading from a URL, which cannot work offline for any app.
```

---

## Quick reference: what to paste where

| Store field | Source |
|---|---|
| Description (body) | `docs/STORE_LISTING.md` → "Description (Store field)" |
| Product features | `docs/STORE_LISTING.md` → "Product features" |
| What's new | `docs/STORE_LISTING.md` → "What's new in this version" |
| Screenshots | `assets/store/01…06-*.png` |
| Box / poster art | `assets/branding/store-boxart-*`, `store-poster-*` |
| Package | `VideoKidnapper.msix` from the MSIX CI run |
| Notes for certification | "Certification notes" block above (always include) |
