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

There are two English listings: **English (United States)**, from the
package, and an additional **English**, which customers in other
English-speaking markets see. Do every step in this section and the next
on **both**, or the second one quietly keeps old copy and screenshots.

- **Description** field: paste the block under *"Description (Store field)"* in `docs/STORE_LISTING.md`.
- **Product features** field: paste the lines under *"Product features"* in `docs/STORE_LISTING.md`, one feature per line (Partner Center shows them as a bulleted list). Up to 20 lines.
- **Short description** (if present): the one-liner under *"Short description"* in the same doc.

These are already written feature-first with no em dashes. Copy verbatim.

## 2. Screenshots

Still in each English listing, under **Screenshots**.

1. Remove the existing screenshots.
2. Upload the files from `assets/store/` (each is exactly 1920×1080, the size the Store requires):
   - `01-edit-1920x1080.png` — Edit: preview, Inspector and track timeline with ranges and a caption
   - `02-export-1920x1080.png` — Export: what to export, platform presets, format, quality, file names
   - `03-captions-1920x1080.png` — the Text inspector styling a caption
   - `04-import-1920x1080.png` — Import: link, file, screen recording and recent projects
   - `05-history-1920x1080.png` — export history with thumbnails
   - `06-setup-1920x1080.png` — the setup screen
3. Order them 01 → 06 (drag to reorder). The first is the hero shot.

To regenerate these after a UI change, run the **Screenshots** workflow
(Actions → Screenshots → Run workflow, theme `light`). It captures on a
Windows runner — real Segoe UI, and an interactive desktop so the grab
works — and uploads `assets/screenshots/*.png` plus the 1920×1080
`assets/store/*.png` as an artifact. Locally: `python
scripts/capture_screenshots.py` then `python scripts/store_screenshots.py`
(macOS needs Screen Recording permission for the terminal first).

## 3. Logo / Store images

Under **Store listings → Store logos** (and the package tiles). The mark
is the retro-stamp badge on navy, one consistent look everywhere:

- **1:1 box art** (1080×1080 / 2160×2160): `assets/branding/store-boxart-1080x1080.png` / `-2160x2160.png`
- **9:16 poster art** (720×1080 / 1440×2160): `assets/branding/store-poster-720x1080.png` / `-1440x2160.png`
- **Tile overrides** (300 / 150 / 71): `assets/branding/store-tile-300x300.png`, etc. — optional; the package already carries matching tiles in `packaging/msix/Assets/`.

You usually don't need to touch these unless the mark changed. `python scripts/make_brand_assets.py` regenerates all of them, plus the package tiles and app icons (see `assets/branding/README.md`).

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

This is the text that lives on the product's **Additional Testing Information** page (Partner Center moved the notes there; the Submission Options page only links to it). It persists across submissions, so it only needs re-pasting if it has been cleared. It exists
because a June 2026 submission was rejected under **Store policy 10.1.2.10
(Functionality)** with *"Unusable Feature: Working offline"* — the tester
disconnected the network, tried to download a video, and saw it fail.
Downloading is inherently online, so the fix (shipped in 1.7.4) was to
make the offline state clear and graceful rather than a cryptic error; the
note tells the reviewer that up front so they don't file the same finding.

```
Testing notes:

VideoKidnapper's download feature fetches video from online services such as YouTube, Reddit, and Instagram, so it requires an active internet connection by design.

When offline, attempting a download immediately shows: "No internet connection. Connect to the internet to download videos. You can still open a local file to trim, caption, and export." The app does not retry, hang, or show a technical DNS error.

All editing works offline. Version 1.9.0 organizes the app as three steps across the top: Import, Edit, Export. In Import, use Browse files (Ctrl+O) to open a local video, or Set up recording to record the screen; a file can also be dropped on the Edit preview. Then trim and add captions or overlays in Edit, and make a GIF or MP4 in Export, all while disconnected.

To verify the previous policy 10.1.2.10 issue is resolved:
1. Launch VideoKidnapper and disconnect LAN or Wi-Fi.
2. In Import, paste a URL into Paste a link, click Download, and confirm the clear offline message appears immediately.
3. Click Browse files and open a local video. In Edit, add a caption with + Text.
4. In Export, click Export and confirm it completes without a network connection.

The only feature that requires a connection is downloading media from an online URL.
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
