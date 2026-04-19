# Winget manifests

Once published, Windows users install with:

```powershell
winget install AES256Afro.VideoKidnapper
```

## Submission flow

Winget manifests live in a central GitHub repo: [`microsoft/winget-pkgs`](https://github.com/microsoft/winget-pkgs). Getting a package listed means opening a PR against that repo with the three-file manifest set under the right namespaced path.

## Per-release steps

After the GitHub Release for a given tag exists and has the installer `.exe` attached:

1. **Get the SHA256** of the uploaded `.exe`:

   ```powershell
   (Get-FileHash -Algorithm SHA256 VideoKidnapper.exe).Hash
   ```

2. **Duplicate this directory** for the new version (e.g. copy `1.2.0/` → `1.3.0/`) and update:
   - every `PackageVersion:` line
   - the `InstallerUrl:` to the new tag's asset URL
   - `InstallerSha256:` to the value from step 1
   - `ReleaseDate:` and `ReleaseNotes:` in the locale file

3. **Validate locally** with Microsoft's manifest validator:

   ```powershell
   winget validate --manifest packaging/winget/manifests/1.2.0
   ```

4. **Submit a PR to `microsoft/winget-pkgs`.** The target path inside that repo is:

   ```
   manifests/a/AES256Afro/VideoKidnapper/1.2.0/
   ```

   Copy the three YAML files there. The repo has a bot that runs an automated review; typical turnaround is hours to a day.

## Manifest file roles

Winget requires three files per version:

| File | Purpose |
|---|---|
| `AES256Afro.VideoKidnapper.yaml` | `version` stub — ties the other two together |
| `AES256Afro.VideoKidnapper.installer.yaml` | URL + SHA256 + installer type |
| `AES256Afro.VideoKidnapper.locale.en-US.yaml` | Display metadata shown in `winget search` |

Additional locales (e.g. `locale.fr-FR.yaml`) are optional — English is the required default.

## Why `InstallerType: portable`

The `.exe` built by PyInstaller is a self-contained single file — it doesn't run an MSI or legacy setup wizard. Winget's `portable` installer type handles exactly this: it copies the file into a managed location and adds the binary to PATH under the `Commands:` name. Uninstall is a simple file removal, no registry entries.
