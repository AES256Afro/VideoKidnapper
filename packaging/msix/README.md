# MSIX / Microsoft Store package

Builds **`VideoKidnapper.msix`** — the Windows package format the Microsoft Store distributes. Store distribution matters for one big reason: **Microsoft signs certified packages**, which eliminates the SmartScreen "unknown publisher" warning that the unsigned portable `.exe` and Inno Setup installer trigger — for a $19 one-time developer registration instead of a $200–400/yr code-signing certificate.

## Layout

| File | Purpose |
|---|---|
| `AppxManifest.template.xml` | Manifest with `{{...}}` placeholders for identity values |
| `Assets/` | Store tiles + taskbar icons generated from the balaclava mark |
| `build-msix.ps1` | Assembles the layout from a PyInstaller exe and runs `makeappx pack` |

The package wraps the **same PyInstaller `VideoKidnapper.exe`** the release workflow builds — MSIX replaces the *installer*, not the binary. `runFullTrust` is required (PyInstaller bootstrap, ffmpeg subprocesses, yt-dlp browser-cookie reads). An `AppExecutionAlias` puts `videokidnapper` on PATH for CLI parity with the pip/deb installs.

**FFmpeg must be bundled** (`-FFmpegDir`): container testing showed the MSIX activation broker does not rebuild PATH from the registry, so PATH-based ffmpeg discovery silently fails inside the container even when ffmpeg is installed system-wide. The app's resolver (`videokidnapper/utils/ffmpeg_check.py`) therefore checks `<exe dir>\assets\ffmpeg\bin` — exactly where `-FFmpegDir` places the binaries. Bundle a GPL build (gyan.dev / BtbN) and link its source in the Store listing, same policy as the AppImage.

## Local build + container test

```powershell
# makeappx/signtool come from the Windows SDK, or lighter: the
# Microsoft.Windows.SDK.BuildTools NuGet package (it's a zip).
.\packaging\msix\build-msix.ps1 -ExePath dist\VideoKidnapper.exe -Version 1.4.0.0

# Self-signed cert for local install (must match the default CN=VideoKidnapperDev):
$cert = New-SelfSignedCertificate -Type CodeSigningCert -Subject "CN=VideoKidnapperDev" -CertStoreLocation Cert:\CurrentUser\My
signtool sign /fd SHA256 /sha1 $cert.Thumbprint dist\VideoKidnapper.msix
# Trust it (admin), then install:
Import-Certificate -FilePath dev.cer -CertStoreLocation Cert:\LocalMachine\TrustedPeople
Add-AppxPackage dist\VideoKidnapper.msix
```

Container findings (2026-07-02, Windows 11 Pro):

- The `videokidnapper` CLI alias activates inside the container and streams
  stdout to the calling shell (exit codes are unreliable for windowed exes —
  judge by output).
- **PATH is not inherited into activation** — neither caller-process PATH
  edits nor fresh registry user-PATH entries reached the container. This is
  why FFmpeg bundling is mandatory (see above).
- With FFmpeg bundled, a real CLI export (ffmpeg subprocess, temp files,
  output written outside the container) succeeds.

## Store submission (per release)

1. **One-time:** register a Partner Center individual developer account ($19) at https://partner.microsoft.com/dashboard/registration and reserve the app name **VideoKidnapper**. Under *Product management → Product identity* you get three values.
2. Build with the real identity (values from step 1):

```powershell
.\packaging\msix\build-msix.ps1 -ExePath dist\VideoKidnapper.exe -Version X.Y.Z.0 `
    -IdentityName "<Package/Identity/Name>" `
    -Publisher "<Package/Identity/Publisher>" `
    -PublisherDisplay "<Package/Properties/PublisherDisplayName>"
```

3. **Do not sign** — the Store signs after certification. Upload the `.msix` in a new submission on Partner Center, fill the listing (description, screenshots from `assets/screenshots/`, privacy policy URL `https://videokidnapper.com/privacy.html`), complete the age-ratings questionnaire, and submit.
4. Certification usually takes 1–3 business days. Expect scrutiny of the downloader functionality — the listing description should emphasize the editor and note that users are responsible for complying with platform terms (mirror the README's disclaimer).

## Version rules

Store versions are four-part `X.Y.Z.0` and the last digit **must be 0** (reserved by the Store). Map app version `1.5.0` → package `1.5.0.0`.
