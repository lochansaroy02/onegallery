# Install One Gallery on Windows with one command (PowerShell or Windows Terminal, no admin rights):
#
#   irm https://raw.githubusercontent.com/lochansaroy02/onegallery/main/install.ps1 | iex
#
# Downloads OneGallery-<version>-setup.exe from the latest GitHub release and runs the installer
# for your user. Running it again updates One Gallery. Your settings, library index and favorites
# live in %APPDATA%\OneGallery and %LOCALAPPDATA%\OneGallery and are never touched.
#
# Options (run it as a script block to pass them):
#   & ([scriptblock]::Create((irm https://raw.githubusercontent.com/lochansaroy02/onegallery/main/install.ps1))) -Version v0.3.0
#
#   -Version vX.Y.Z   install that release instead of the latest one
#   -Restart          reopen One Gallery afterwards if it was running
#
# The same thing for macOS and Linux is install.sh.

param(
    [string]$Version = "",
    [switch]$Restart
)

$Repo = "lochansaroy02/onegallery"
if ($Version -and -not $Version.StartsWith("v")) { $Version = "v$Version" }
# AppId from packaging/windows/onegallery.iss: Inno Setup's uninstall key is "<AppId>_is1"
$UninstallKey = "Software\Microsoft\Windows\CurrentVersion\Uninstall\{6F1C2B7E-4A8D-4D6B-9E3A-5C2F1E8B7A90}_is1"

function Write-Bold([string]$Text) { Write-Host $Text -ForegroundColor White }
function Write-Info([string]$Text) { Write-Host "  $Text" }

# the URL of the release asset whose name ends with $Suffix
function Get-ReleaseAsset([string]$Suffix) {
    if ($Version) {
        $api = "https://api.github.com/repos/$Repo/releases/tags/$Version"
    } else {
        $api = "https://api.github.com/repos/$Repo/releases/latest"
    }
    $label = if ($Version) { $Version } else { "latest" }
    try {
        $release = Invoke-RestMethod -Uri $api -Headers @{ Accept = "application/vnd.github+json" } -UseBasicParsing
    } catch {
        throw "Could not read the $label release from GitHub (offline, or no such release?): $($_.Exception.Message)"
    }
    $asset = $release.assets | Where-Object { $_.name -like "*$Suffix" } | Select-Object -First 1
    if (-not $asset) {
        throw "The $label release has no *$Suffix download (https://github.com/$Repo/releases)"
    }
    return $asset
}

# where an earlier install put OneGallery.exe (per-user or all-users), or $null
function Get-InstalledExe {
    foreach ($hive in "HKCU:", "HKLM:") {
        $key = Get-ItemProperty -Path "$hive\$UninstallKey" -ErrorAction SilentlyContinue
        if ($key -and $key.InstallLocation) {
            $exe = Join-Path $key.InstallLocation "OneGallery.exe"
            if (Test-Path $exe) { return $exe }
        }
    }
    return $null
}

function Install-OneGallery {
    if (-not [Environment]::Is64BitOperatingSystem) {
        throw "One Gallery needs 64-bit Windows."
    }
    if ([Environment]::OSVersion.Version.Build -lt 17763) {
        throw "One Gallery needs Windows 10 version 1809 or newer, or Windows 11."
    }
    # Windows PowerShell 5.1 defaults to TLS 1.0, which GitHub refuses
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

    $asset = Get-ReleaseAsset "-setup.exe"
    $tmp = Join-Path ([IO.Path]::GetTempPath()) ("onegallery-" + [Guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $tmp | Out-Null
    try {
        $exe = Join-Path $tmp $asset.name
        Write-Bold ("Downloading {0} ({1:N0} MB)" -f $asset.name, ($asset.size / 1MB))
        # the progress bar makes Invoke-WebRequest many times slower on Windows PowerShell 5.1
        $oldProgress = $ProgressPreference
        $ProgressPreference = "SilentlyContinue"
        try {
            Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $exe -UseBasicParsing
        } catch {
            throw "Download failed: $($_.Exception.Message)"
        } finally {
            $ProgressPreference = $oldProgress
        }

        $wasRunning = [bool](Get-Process -Name OneGallery -ErrorAction SilentlyContinue)

        Write-Bold "Running the One Gallery installer"
        Write-Info "It installs for your user, no admin rights needed. A running One Gallery is closed first."
        # Inno Setup: /SILENT shows only a progress window, /CURRENTUSER skips the admin prompt
        $setup = Start-Process -FilePath $exe -Wait -PassThru -ArgumentList @(
            "/SILENT", "/CURRENTUSER", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS")
        if ($setup.ExitCode -ne 0) {
            throw "The installer did not finish (exit code $($setup.ExitCode))."
        }
    } finally {
        Remove-Item -Recurse -Force -Path $tmp -ErrorAction SilentlyContinue
    }

    $installed = Get-InstalledExe
    if ($installed) { Write-Info "Installed $installed" }
    if ($wasRunning -and $Restart -and $installed) {
        Start-Process -FilePath $installed
        Write-Info "One Gallery restarted."
    } elseif ($wasRunning) {
        Write-Info "Open One Gallery again to use the new version."
    } else {
        Write-Info "Open One Gallery from the Start menu."
    }
    Write-Bold "Install complete."
}

# report errors without "exit": under "irm | iex" that would close the user's PowerShell window
try {
    Install-OneGallery
} catch {
    Write-Host "Error: $($_.Exception.Message)" -ForegroundColor Red
}
