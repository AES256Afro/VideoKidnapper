# Brand assets

The VideoKidnapper mark is a balaclava (ski-mask) head — a flat, single-color
pictogram with the eye holes and mouth as true cutouts, so it works on any
background. Accent color is `#2860D0`; the app's dark surface is `#0D1117`.

| File | What it is |
|---|---|
| `logo.svg` | Master mark, accent blue. **Edit this**, then regenerate the PNGs below. |
| `logo-white.svg` | Same geometry, white — for dark backgrounds. |
| `logo-512.png` / `logo-1024.png` | Transparent square mark (used by the app icon, AppImage, favicon). |
| `logo-lockup.png` | Horizontal mark + wordmark, light text — for dark backgrounds. |
| `logo-lockup-onlight.png` | Lockup with dark text — for light backgrounds. |
| `logo-lockup-dark.png` | Lockup on the dark brand card — social / hero. |
| `logo-card-1280x720.png` | Mark + wordmark, 16:9 dark card — social preview. |
| `store-poster-{720x1080,1440x2160}.png` | Microsoft Store 2:3 poster art. |
| `store-boxart-{1080x1080,2160x2160}.png` | Store 1:1 box art (mark + wordmark). |
| `store-tile-{300x300,150x150,71x71}.png` | Store 1:1 tile-icon overrides (the MSIX already bundles its own). |

The `.ico` / multi-size window icon lives at `videokidnapper/assets/icon.ico`
(shipped as package data); it's regenerated from `logo.svg`. See
`packaging/msix/Assets/` for the Store tiles baked into the MSIX.
