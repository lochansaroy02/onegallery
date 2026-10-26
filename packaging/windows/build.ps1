<#
.SYNOPSIS
    Build One Gallery for Windows: dist\OneGallery\OneGallery.exe and the installer
    dist\OneGallery-<version>-setup.exe.

.DESCRIPTION
    Run from any folder on Windows 10/11 (PowerShell 5.1 or 7):

        powershell -ExecutionPolicy Bypass -File packaging\windows\build.ps1

    Needs Python 3.11-3.13 (python.org or "winget install Python.Python.3.13") and Inno Setup 6
    ("winget install JRSoftware.InnoSetup"). It creates build\venv, installs the Python
    packages, downloads ffmpeg (LGPL build) for video thumbnails, runs the unit tests,
    builds with PyInstaller, checks the packaged app with OneGallery.exe --self-test and
    packs the installer with Inno Setup.

.PARAMETER NoFaces
    Leave out OpenCV (People / face grouping); the installer gets about 40 MB smaller.

.PARAMETER NoFfmpeg
    Don't bundle ffmpeg (no video thumbnails or frame capture; playback still works).

.PARAMETER SkipTests
    Skip the unit tests.

.PARAMETER NoInstaller
    Stop after PyInstaller (dist\OneGallery\OneGallery.exe), without building the installer.
#>
param(
    [switch]$NoFaces,
    [switch]$NoFfmpeg,
    [switch]$SkipTests,
    [switch]$NoInstaller
)
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"   # Invoke-WebRequest is very slow with the progress bar

$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $root
function Step($text) { Write-Host "`n==> $text" -ForegroundColor Cyan }
function Run($exe) {
    & $exe @args
    if ($LASTEXITCODE -ne 0) { throw "$exe $args failed (exit $LASTEXITCODE)" }
}

$version = (Select-String -Path backend\__init__.py -Pattern '__version__ = "([^"]+)"').Matches[0].Groups[1].Value
Write-Host "One Gallery $version" -ForegroundColor Green

# ---- 1. Python environment -----------------------------------------------------------------
Step "Python environment (build\venv)"
if (-not (Test-Path build\venv\Scripts\python.exe)) {
    if (Get-Command py -ErrorAction SilentlyContinue) { Run py -3 -m venv build\venv }
    else { Run python -m venv build\venv }
}
$py = (Resolve-Path build\venv\Scripts\python.exe).Path
Run $py -m pip install --quiet --upgrade pip
$packages = @("-r", "requirements.txt", "pyinstaller", "send2trash", "watchdog", "pillow-heif")
if (-not $NoFaces) { $packages += "opencv-python-headless" }
Run $py -m pip install --quiet @packages

# ---- 2. ffmpeg --------------------------------------------------------------------------------
if (-not $NoFfmpeg) {
    Step "ffmpeg (LGPL build from github.com/BtbN/FFmpeg-Builds)"
    $ff = Join-Path $root "build\ffmpeg"
    if (-not (Test-Path "$ff\ffmpeg.exe")) {
        New-Item -ItemType Directory -Force -Path $ff | Out-Null
        $zip = Join-Path $env:TEMP "onegallery-ffmpeg.zip"
        $url = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-lgpl.zip"
        Invoke-WebRequest -Uri $url -OutFile $zip
        $unpacked = Join-Path $env:TEMP "onegallery-ffmpeg"
        if (Test-Path $unpacked) { Remove-Item -Recurse -Force $unpacked }
        Expand-Archive -Path $zip -DestinationPath $unpacked
        $bin = Get-ChildItem -Path $unpacked -Recurse -Filter ffmpeg.exe | Select-Object -First 1
        Copy-Item (Join-Path $bin.DirectoryName "ffmpeg.exe"), (Join-Path $bin.DirectoryName "ffprobe.exe") $ff
        $license = Get-ChildItem -Path $unpacked -Recurse -Filter LICENSE.txt | Select-Object -First 1
        if ($license) { Copy-Item $license.FullName "$ff\LICENSE.txt" }
        Remove-Item -Recurse -Force $unpacked, $zip
    }
    $env:ONEGALLERY_FFMPEG_DIR = $ff
} else {
    $env:ONEGALLERY_FFMPEG_DIR = Join-Path $root "build\no-ffmpeg"
}

# ---- 3. tests --------------------------------------------------------------------------------
if (-not $SkipTests) {
    Step "Unit tests"
    $env:QT_QPA_PLATFORM = "offscreen"
    if (-not $NoFfmpeg) { $env:PATH = "$env:ONEGALLERY_FFMPEG_DIR;$env:PATH" }
    Run $py -m unittest discover -s tests
    Remove-Item Env:QT_QPA_PLATFORM
}

# ---- 4. PyInstaller -----------------------------------------------------------------------------
Step "PyInstaller (dist\OneGallery)"
if (Test-Path dist\OneGallery) { Remove-Item -Recurse -Force dist\OneGallery }
Run $py -m PyInstaller packaging\windows\onegallery.spec --noconfirm --distpath dist --workpath build\pyinstaller

Step "Checking the packaged app (OneGallery.exe --self-test)"
$report = Join-Path $root "build\self-test.txt"
$proc = Start-Process -FilePath dist\OneGallery\OneGallery.exe -ArgumentList "--self-test", "`"$report`"" -Wait -PassThru
Get-Content $report | ForEach-Object { Write-Host "    $_" }
if ($proc.ExitCode -ne 0) {
    if ($NoFfmpeg -and ((Get-Content $report) -match "FAIL ffmpeg") -and -not ((Get-Content $report) -match "FAIL (?!ffmpeg)")) {
        Write-Host "    (ffmpeg left out on purpose)"
    } else {
        throw "the packaged app failed its self-test (see above)"
    }
}
if ($NoInstaller) { Write-Host "`nDone: dist\OneGallery\OneGallery.exe" -ForegroundColor Green; exit 0 }

# ---- 5. installer (Inno Setup) -------------------------------------------------------------------
Step "Installer (Inno Setup)"
$iscc = @(
    (Get-Command iscc -ErrorAction SilentlyContinue).Source,
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
) | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
if (-not $iscc) { throw "Inno Setup 6 not found. Install it: winget install JRSoftware.InnoSetup" }
Run $iscc "/Qp" "/DAppVersion=$version" packaging\windows\onegallery.iss

$setup = "dist\OneGallery-$version-setup.exe"
$size = "{0:N0} MB" -f ((Get-Item $setup).Length / 1MB)
Write-Host "`nDone: $setup ($size)" -ForegroundColor Green
