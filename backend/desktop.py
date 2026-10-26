"""Set a picture as the desktop wallpaper and / or the lock screen background.

KDE Plasma: `plasma-apply-wallpaperimage` for the desktop (every screen) and
kscreenlockerrc (via kwriteconfig6 / kwriteconfig5) for the lock screen. Windows:
SystemParametersInfo for the desktop and the WinRT LockScreen API (through PowerShell)
for the lock screen. GNOME and macOS desktops are handled too.

The picture is first copied (upright, as JPEG or PNG) to ~/.local/share/onegallery/wallpapers,
so the wallpaper keeps working when the original is edited, moved, deleted or on a drive
that gets unmounted.
"""

import hashlib
import logging
import os
import shutil
import subprocess
import sys

from PIL import Image, ImageOps

from . import DATA_DIR, IS_WINDOWS, NO_WINDOW

log = logging.getLogger(__name__)

WALLPAPER_DIR = DATA_DIR / "wallpapers"
KEEP = 8          # older copies are removed, the newest ones may still be in use
MAX_EDGE = 7680   # 8K is plenty for any screen
TIMEOUT = 20
TARGETS = ("wallpaper", "lockscreen", "both")


class WallpaperError(RuntimeError):
    pass


def _run(cmd: list[str]) -> None:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT,
                             stdin=subprocess.DEVNULL, **NO_WINDOW)
    except (OSError, subprocess.SubprocessError) as exc:
        raise WallpaperError(f"{os.path.basename(cmd[0])} failed: {exc}") from exc
    if out.returncode != 0:
        detail = (out.stderr or out.stdout).strip().splitlines()
        raise WallpaperError(detail[-1] if detail else f"{os.path.basename(cmd[0])} failed")


def prepare(path: str) -> str:
    """Upright copy of path in WALLPAPER_DIR (JPEG, or PNG for pictures with transparency)."""
    st = os.stat(path)
    key = hashlib.sha1(f"{path}\0{st.st_mtime}\0{st.st_size}".encode("utf-8", "surrogateescape"))
    WALLPAPER_DIR.mkdir(parents=True, exist_ok=True)
    with Image.open(path) as im:
        im = ImageOps.exif_transpose(im)
        alpha = im.mode in ("RGBA", "LA", "PA") or (im.mode == "P" and "transparency" in im.info)
        if max(im.size) > MAX_EDGE:
            im.thumbnail((MAX_EDGE, MAX_EDGE), Image.LANCZOS)
        ext = ".png" if alpha else ".jpg"
        name = os.path.splitext(os.path.basename(path))[0][:60]
        out = WALLPAPER_DIR / f"{name}-{key.hexdigest()[:10]}{ext}"
        if not out.exists():
            tmp = out.with_suffix(".tmp")
            if alpha:
                im.convert("RGBA").save(tmp, "PNG")
            else:
                im.convert("RGB").save(tmp, "JPEG", quality=95)
            os.replace(tmp, out)
    os.utime(out)  # newest = in use
    _prune(keep=out)
    return str(out)


def _prune(keep) -> None:
    files = sorted((p for p in WALLPAPER_DIR.iterdir() if p.is_file()),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    for old in files[KEEP:]:
        if old != keep:
            try:
                old.unlink()
            except OSError:
                pass


# Windows lock screen: Windows.System.UserProfile.LockScreen.SetImageFileAsync (WinRT),
# reachable from the built-in Windows PowerShell 5.1. The path comes in $env:LG_IMAGE.
_WIN_LOCKSCREEN_PS = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$methods = [System.WindowsRuntimeSystemExtensions].GetMethods()
$asTaskAction = $methods | Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncAction' } | Select-Object -First 1
$asTaskOp = $methods | Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' } | Select-Object -First 1
[void][Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
[void][Windows.System.UserProfile.LockScreen, Windows.System.UserProfile, ContentType = WindowsRuntime]
$op = [Windows.Storage.StorageFile]::GetFileFromPathAsync($env:LG_IMAGE)
$file = $asTaskOp.MakeGenericMethod([Windows.Storage.StorageFile]).Invoke($null, @($op)).Result
$asTaskAction.Invoke($null, @([Windows.System.UserProfile.LockScreen]::SetImageFileAsync($file))).Wait()
"""


def _windows_desktop(image: str) -> None:
    import ctypes

    SPI_SETDESKWALLPAPER, SPIF_UPDATEINIFILE, SPIF_SENDCHANGE = 0x0014, 0x01, 0x02
    ok = ctypes.windll.user32.SystemParametersInfoW(
        SPI_SETDESKWALLPAPER, 0, image, SPIF_UPDATEINIFILE | SPIF_SENDCHANGE)
    if not ok:
        raise WallpaperError("Windows refused the wallpaper")


def _windows_lockscreen(image: str) -> None:
    shell = shutil.which("powershell") or "powershell.exe"
    env = dict(os.environ, LG_IMAGE=image)
    try:
        out = subprocess.run([shell, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                              "-Command", _WIN_LOCKSCREEN_PS],
                             capture_output=True, text=True, timeout=TIMEOUT, env=env,
                             stdin=subprocess.DEVNULL, **NO_WINDOW)
    except (OSError, subprocess.SubprocessError) as exc:
        raise WallpaperError(f"PowerShell failed: {exc}") from exc
    if out.returncode != 0:
        detail = (out.stderr or out.stdout).strip().splitlines()
        raise WallpaperError("Couldn't set the lock screen" + (f": {detail[0]}" if detail else "")
                             + " (it may be managed by your organisation)")


def _gsettings_available() -> bool:
    return bool(shutil.which("gsettings")) and "GNOME" in os.environ.get("XDG_CURRENT_DESKTOP", "").upper()


def set_desktop(image: str) -> None:
    uri = "file://" + image
    if IS_WINDOWS:
        _windows_desktop(image)
    elif shutil.which("plasma-apply-wallpaperimage"):
        _run(["plasma-apply-wallpaperimage", image])
    elif _gsettings_available():
        _run(["gsettings", "set", "org.gnome.desktop.background", "picture-uri", uri])
        _run(["gsettings", "set", "org.gnome.desktop.background", "picture-uri-dark", uri])
    elif sys.platform == "darwin":
        script = f'tell application "System Events" to tell every desktop to set picture to POSIX file "{image}"'
        _run(["osascript", "-e", script])
    else:
        raise WallpaperError("Setting the wallpaper needs KDE Plasma (plasma-apply-wallpaperimage)")


def set_lockscreen(image: str) -> None:
    uri = "file://" + image
    kwc = None if IS_WINDOWS else shutil.which("kwriteconfig6") or shutil.which("kwriteconfig5")
    if IS_WINDOWS:
        _windows_lockscreen(image)
    elif kwc:
        base = [kwc, "--file", "kscreenlockerrc", "--group", "Greeter"]
        _run(base + ["--key", "WallpaperPlugin", "org.kde.image"])
        image_group = base + ["--group", "Wallpaper", "--group", "org.kde.image", "--group", "General"]
        _run(image_group + ["--key", "Image", uri])
        _run(image_group + ["--key", "PreviewImage", uri])
    elif _gsettings_available():
        _run(["gsettings", "set", "org.gnome.desktop.screensaver", "picture-uri", uri])
    else:
        raise WallpaperError("Setting the lock screen needs KDE Plasma (kwriteconfig6)")


def apply(path: str, target: str) -> str:
    """Set path as the wallpaper / lock screen / both. Runs in a worker. Returns target."""
    if target not in TARGETS:
        raise WallpaperError(f"unknown target {target!r}")
    try:
        image = prepare(path)
    except FileNotFoundError as exc:
        raise WallpaperError("The picture is not available") from exc
    except OSError as exc:
        raise WallpaperError(f"Can't read the picture: {exc}") from exc
    if target in ("wallpaper", "both"):
        set_desktop(image)
    if target in ("lockscreen", "both"):
        set_lockscreen(image)
    return target
