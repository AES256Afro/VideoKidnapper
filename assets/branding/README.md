# Brand assets

The VideoKidnapper mark is a **retro stamp**: a cream badge with a navy rim,
"VIDEO KIDNAPPER" across the top, the app's steps (DOWNLOAD ✦ TRIM ✦
CAPTION ✦ EXPORT) along the bottom, and the balaclava on a navy disc in the
middle. Below about 64 px the ring text turns to noise, so small sizes use a
**ring-free mark**: the balaclava on a navy disc with a thin cream rim.

| Colour | Hex | Used for |
|---|---|---|
| Cream | `#F3E9D2` | badge disc, mask, wordmark on dark |
| Navy | `#1F2A44` | rim, inner disc, ring text, wordmark on light |
| Orange | `#E4572E` | stars, dot, "Kidnapper" on light |
| Light orange | `#F28B6B` | "Kidnapper" on dark |

Type: ring text in **Space Mono Bold**, wordmark in **Alfa Slab One**. Both are
under the SIL Open Font License; the files and licences are in `fonts/`.

**Everything here is generated. Don't edit the files; edit
`scripts/make_brand_assets.py` and run it:**

```
pip install fonttools
python scripts/make_brand_assets.py
```

It converts all text to outlines, so the SVGs render the same anywhere,
including in an `<img>` that can't load web fonts. PNGs are rendered with
headless Chrome or Edge (`VK_CHROME` overrides the lookup). One run rewrites
this folder, the MSIX tiles and the app icons.

| File | What it is |
|---|---|
| `logo.svg` | The badge. |
| `logo-mark.svg` | Ring-free mark, for small sizes and favicons. |
| `logo-white.svg` | Ring-free mark inverted (cream disc, navy mask), for dark backgrounds. |
| `logo-512.png` / `logo-1024.png` | The badge, transparent (AppImage and .deb icon, apple-touch-icon). |
| `favicon-64.png` | Ring-free mark, PNG favicon fallback. |
| `logo-lockup.png` | Badge + wordmark, light text, for dark backgrounds. |
| `logo-lockup-onlight.png` | Badge + wordmark, dark text, for light backgrounds. |
| `logo-lockup-dark.png` | Badge + wordmark on a navy card. |
| `logo-card-1280x720.png` | Badge over the wordmark on navy, 16:9: social preview (`og:image`). |
| `store-poster-{720x1080,1440x2160}.png` | Microsoft Store 2:3 poster art. |
| `store-boxart-{1080x1080,2160x2160}.png` | Microsoft Store 1:1 box art. |
| `store-tile-{300x300,150x150,71x71}.png` | Store tile overrides (the MSIX already bundles its own). |
| `store-hero-{1920x1080,3840x2160}.png` | Store 16:9 super hero art: the ring-free mark beside the Edit screenshot. The Store forbids the product name here, so it has no badge and the screenshot's header is cropped off. Rebuild it after recapturing screenshots. |

Outside this folder, the same run writes:

- `videokidnapper/assets/icon.ico` (16 to 256 px), `icon.icns` (16 to 1024 px)
  and `icon.png` (256 px): the window, taskbar and Dock icons. Sizes under
  64 px use the ring-free mark.
- `videokidnapper/assets/mark.png`: the ring-free mark in the app header.
- `packaging/msix/Assets/*.png`: the tiles and taskbar icons baked into the
  Store package.
