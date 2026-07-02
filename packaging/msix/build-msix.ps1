# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
#
# Assemble VideoKidnapper.msix from a PyInstaller VideoKidnapper.exe.
#
#   .\packaging\msix\build-msix.ps1 -ExePath dist\VideoKidnapper.exe -Version 1.4.0.0
#
# Local test builds use the CN=VideoKidnapperDev defaults (sign with a
# matching self-signed cert to install). Store builds must pass the
# Partner Center identity values:
#
#   .\packaging\msix\build-msix.ps1 -ExePath dist\VideoKidnapper.exe -Version 1.4.0.0 `
#       -IdentityName "12345AES256Afro.VideoKidnapper" `
#       -Publisher "CN=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" `
#       -PublisherDisplay "AES256Afro"
#
# makeappx.exe comes from the Windows SDK or the
# Microsoft.Windows.SDK.BuildTools NuGet package; pass -MakeAppx if it
# is not on PATH. Store submissions do NOT need local signing —
# Microsoft signs after certification.
param(
    [Parameter(Mandatory)] [string]$ExePath,
    [Parameter(Mandatory)] [string]$Version,          # four-part, e.g. 1.4.0.0
    [string]$IdentityName = "VideoKidnapperDev",
    [string]$Publisher = "CN=VideoKidnapperDev",
    [string]$PublisherDisplay = "AES256Afro",
    [string]$MakeAppx = "makeappx.exe",
    # Directory containing ffmpeg.exe + ffprobe.exe to bundle at
    # assets\ffmpeg\bin inside the package. Bundling is effectively
    # required for MSIX: PATH inside the app container is unreliable,
    # and the app's resolver checks next to its exe (see
    # videokidnapper/utils/ffmpeg_check.py). GPL-build note: link the
    # ffmpeg source in the Store listing / release notes.
    [string]$FFmpegDir = "",
    [string]$OutFile = "dist\VideoKidnapper.msix"
)
$ErrorActionPreference = "Stop"
$msixDir = $PSScriptRoot

$layout = Join-Path ([System.IO.Path]::GetTempPath()) ("vk-msix-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $layout | Out-Null
try {
    Copy-Item $ExePath (Join-Path $layout "VideoKidnapper.exe")
    Copy-Item (Join-Path $msixDir "Assets") (Join-Path $layout "Assets") -Recurse

    if ($FFmpegDir) {
        $ffDest = Join-Path $layout "assets\ffmpeg\bin"
        New-Item -ItemType Directory -Path $ffDest -Force | Out-Null
        foreach ($bin in "ffmpeg.exe", "ffprobe.exe") {
            $src = Join-Path $FFmpegDir $bin
            if (-not (Test-Path $src)) { throw "FFmpegDir is missing $bin" }
            Copy-Item $src $ffDest
        }
    }

    $manifest = Get-Content (Join-Path $msixDir "AppxManifest.template.xml") -Raw
    $manifest = $manifest.Replace("{{IDENTITY_NAME}}", $IdentityName)
    $manifest = $manifest.Replace("{{PUBLISHER}}", $Publisher)
    $manifest = $manifest.Replace("{{PUBLISHER_DISPLAY}}", $PublisherDisplay)
    $manifest = $manifest.Replace("{{VERSION}}", $Version)
    Set-Content -Path (Join-Path $layout "AppxManifest.xml") -Value $manifest -Encoding utf8

    $outDir = Split-Path $OutFile -Parent
    if ($outDir -and -not (Test-Path $outDir)) { New-Item -ItemType Directory -Path $outDir | Out-Null }
    & $MakeAppx pack /d $layout /p $OutFile /o
    if ($LASTEXITCODE -ne 0) { throw "makeappx failed with exit code $LASTEXITCODE" }
    Get-Item $OutFile | Select-Object FullName, @{n="MB";e={[int]($_.Length/1MB)}}
}
finally {
    Remove-Item $layout -Recurse -Force -ErrorAction SilentlyContinue
}
