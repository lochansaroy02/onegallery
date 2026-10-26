"""File actions: trash, open / open with, show in file manager, clipboard."""

import configparser
import glob
import logging
import os
import shlex
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from PySide6.QtCore import QFile, QMimeData, QMimeDatabase, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication

from . import IS_MAC, IS_WINDOWS, NO_WINDOW
from .settings import mount_point

log = logging.getLogger(__name__)

try:
    from send2trash import send2trash as _send2trash
except ImportError:
    _send2trash = None


# ---- trash ---------------------------------------------------------------------
def _home_trash() -> Path:
    base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return Path(base) / "Trash"


def _trash_dir_for(path: str) -> tuple[Path, Path | None]:
    """Trash directory for path per the freedesktop spec, plus the top dir that
    stored paths are relative to (None for the home trash, which stores absolute paths)."""
    home_trash = _home_trash()
    home_trash.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.stat(path).st_dev == os.stat(home_trash).st_dev:
        return home_trash, None
    top = Path(mount_point(path))
    uid = os.getuid()
    shared = top / ".Trash"
    if shared.is_dir() and not shared.is_symlink() and shared.stat().st_mode & 0o1000:
        return shared / str(uid), top
    return top / f".Trash-{uid}", top


def freedesktop_trash(path: str) -> None:
    """Minimal implementation of the freedesktop.org Trash spec (used without send2trash)."""
    path = os.path.abspath(path)
    trash, top = _trash_dir_for(path)
    files, info = trash / "files", trash / "info"
    files.mkdir(parents=True, exist_ok=True, mode=0o700)
    info.mkdir(parents=True, exist_ok=True, mode=0o700)
    stem, ext = os.path.splitext(os.path.basename(path))
    name, n = stem + ext, 1
    while True:
        try:
            fd = os.open(info / f"{name}.trashinfo", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            break
        except FileExistsError:
            n += 1
            name = f"{stem}.{n}{ext}"
    stored = os.path.relpath(path, top) if top else path
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write("[Trash Info]\n")
        f.write(f"Path={quote(stored)}\n")
        f.write(f"DeletionDate={datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}\n")
    try:
        os.rename(path, files / name)
    except OSError:
        os.unlink(info / f"{name}.trashinfo")
        raise


def trash_files(paths: list[str]) -> tuple[list[str], list[str]]:
    """Move files to the trash. Returns (trashed, failed). Runs in a worker."""
    trashed, failed = [], []
    for p in paths:
        try:
            if not os.path.exists(p):
                trashed.append(p)  # already gone: just drop it from the index
                continue
            if IS_MAC:
                if not QFile.moveToTrash(p):
                    raise OSError("macOS refused to move it to the Trash")
            elif _send2trash is not None:
                _send2trash(p)  # Recycle Bin on Windows, freedesktop trash on Linux
            elif IS_WINDOWS:
                raise RuntimeError("the Recycle Bin needs send2trash (bundled with the installer)")
            else:
                freedesktop_trash(p)
            trashed.append(p)
        except Exception as exc:
            log.warning("could not trash %s: %s", p, exc)
            failed.append(p)
    return trashed, failed


# ---- clipboard -------------------------------------------------------------------
def copy_text(text: str) -> None:
    QGuiApplication.clipboard().setText(text)


def copy_files(paths: list[str]) -> None:
    """Put files on the clipboard so they can be pasted into Dolphin, chat apps, etc."""
    urls = [QUrl.fromLocalFile(p) for p in paths]
    mime = QMimeData()
    mime.setUrls(urls)
    mime.setText("\n".join(paths))
    payload = "copy\n" + "\n".join(u.toString() for u in urls)
    mime.setData("x-special/gnome-copied-files", payload.encode())
    QGuiApplication.clipboard().setMimeData(mime)


# ---- opening -------------------------------------------------------------------------
def open_default(path: str) -> bool:
    return QDesktopServices.openUrl(QUrl.fromLocalFile(path))


def show_in_folder_blocking(path: str) -> bool:
    """Ask the file manager (Dolphin, Explorer, Finder) to open the folder with the file selected."""
    if IS_WINDOWS:
        # explorer.exe exits with 1 even when it worked
        subprocess.Popen(["explorer", "/select,", os.path.normpath(path)], **NO_WINDOW)
        return True
    if sys.platform == "darwin":
        return subprocess.run(["open", "-R", path], timeout=5).returncode == 0
    if shutil.which("dbus-send"):
        try:
            result = subprocess.run(
                ["dbus-send", "--session", "--print-reply",
                 "--dest=org.freedesktop.FileManager1", "--type=method_call",
                 "/org/freedesktop/FileManager1", "org.freedesktop.FileManager1.ShowItems",
                 "array:string:file://" + quote(path), "string:"],
                capture_output=True, timeout=5,
            )
            if result.returncode == 0:
                return True
        except (OSError, subprocess.TimeoutExpired):
            pass
    return False


def open_folder(path: str) -> bool:
    return QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(path)))


def _app_dirs() -> list[str]:
    data_home = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    data_dirs = (os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share").split(":")
    dirs = [data_home] + data_dirs + [
        os.path.expanduser("~/.local/share/flatpak/exports/share"),
        "/var/lib/flatpak/exports/share",
    ]
    return [os.path.join(d, "applications") for d in dirs if d]


def apps_for_file(path: str) -> list[dict]:
    """Desktop applications that declare support for the file's MIME type."""
    if IS_MAC:
        from . import macos
        return macos.apps_for_file(path)
    mime = QMimeDatabase().mimeTypeForFile(path)
    wanted = {mime.name(), *mime.parentMimeTypes(), *mime.aliases()}
    wanted.add(mime.name().split("/")[0] + "/*")
    apps, seen = [], set()
    for appdir in _app_dirs():
        for desktop in sorted(glob.glob(os.path.join(appdir, "**", "*.desktop"), recursive=True)):
            desktop_id = os.path.relpath(desktop, appdir).replace(os.sep, "-")
            if desktop_id in seen:
                continue
            seen.add(desktop_id)
            entry = _read_desktop(desktop)
            if not entry:
                continue
            types = {t for t in entry.get("MimeType", "").split(";") if t}
            if types & wanted:
                apps.append({"id": desktop_id, "name": entry.get("Name", desktop_id),
                             "icon": entry.get("Icon", ""), "file": desktop})
    apps.sort(key=lambda a: a["name"].lower())
    return apps


def _read_desktop(path: str) -> dict | None:
    parser = configparser.RawConfigParser(strict=False, interpolation=None)
    parser.optionxform = str
    try:
        parser.read(path, encoding="utf-8")
        entry = parser["Desktop Entry"]
    except (configparser.Error, KeyError, UnicodeDecodeError, OSError):
        return None
    if entry.get("Type", "Application") != "Application":
        return None
    if entry.get("NoDisplay", "false").lower() == "true" or entry.get("Hidden", "false").lower() == "true":
        return None
    if not entry.get("Exec"):
        return None
    return dict(entry)


def windows_open_with(path: str) -> bool:
    """Windows' own "Open with" chooser for a file."""
    try:
        subprocess.Popen(["rundll32.exe", "shell32.dll,OpenAs_RunDLL", os.path.normpath(path)], **NO_WINDOW)
        return True
    except OSError as exc:
        log.warning("Open with failed for %s: %s", path, exc)
        return False


def windows_default_apps() -> bool:
    """Windows Settings > Default apps, on One Gallery's page when Windows 11 supports it."""
    return QDesktopServices.openUrl(QUrl("ms-settings:defaultapps?registeredAppUser=OneGallery"))


def launch_desktop_app(desktop_file: str, paths: list[str]) -> bool:
    if IS_MAC:  # desktop_file is the .app path from apps_for_file
        from . import macos
        return macos.open_with(desktop_file, paths)
    entry = _read_desktop(desktop_file)
    if not entry:
        return False
    try:
        args = shlex.split(entry["Exec"])
    except ValueError:
        return False
    cmd = []
    for arg in args:
        if arg in ("%f", "%u"):
            cmd.append(paths[0])
        elif arg in ("%F", "%U"):
            cmd.extend(paths)
        elif arg == "%i":
            if entry.get("Icon"):
                cmd += ["--icon", entry["Icon"]]
        elif arg == "%c":
            cmd.append(entry.get("Name", ""))
        elif arg == "%k":
            cmd.append(desktop_file)
        else:
            cmd.append(arg.replace("%%", "%"))
    if not any(p in cmd for p in paths):
        cmd.append(paths[0])
    try:
        subprocess.Popen(cmd, start_new_session=True, stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except OSError as exc:
        log.warning("could not launch %s: %s", cmd, exc)
        return False


# ---- default image viewer ------------------------------------------------------------------
DESKTOP_ID = "onegallery.desktop"
VIEWER_MIMES = ["image/jpeg", "image/png", "image/webp", "image/gif", "image/bmp", "image/tiff"]
HEIF_MIMES = ["image/heic", "image/heif"]


def _mimeapps_path() -> str:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, "mimeapps.list")


def _read_mimeapps() -> configparser.RawConfigParser:
    parser = configparser.RawConfigParser(strict=False, interpolation=None, delimiters=("=",))
    parser.optionxform = str
    try:
        parser.read(_mimeapps_path(), encoding="utf-8")
    except (configparser.Error, UnicodeDecodeError):
        pass
    return parser


def desktop_file_installed() -> bool:
    return any(os.path.exists(os.path.join(d, DESKTOP_ID)) for d in _app_dirs())


def default_viewer_status(mimes: list[str]) -> str:
    """"default" | "partial" | "other" | "not-installed" (no onegallery.desktop to point at),
    or "windows" (Windows decides in Settings > Default apps)."""
    if IS_WINDOWS:
        return "windows"
    if IS_MAC:
        from . import macos
        return macos.default_viewer_status(mimes)
    if not desktop_file_installed():
        return "not-installed"
    parser = _read_mimeapps()
    section = parser["Default Applications"] if parser.has_section("Default Applications") else {}
    ours = [m for m in mimes if section.get(m, "").split(";")[0].strip() == DESKTOP_ID]
    if len(ours) == len(mimes):
        return "default"
    return "partial" if ours else "other"


def set_default_viewer(mimes: list[str]) -> None:
    """Make Gallery the default app for the image types (writes ~/.config/mimeapps.list)."""
    if IS_MAC:
        from . import macos
        return macos.set_default_viewer(mimes)
    if not desktop_file_installed():
        raise RuntimeError("Install the launcher first (packaging/install-user.sh or the Arch package)")
    done = False
    if shutil.which("xdg-mime"):
        result = subprocess.run(["xdg-mime", "default", DESKTOP_ID, *mimes],
                                capture_output=True, timeout=15)
        done = result.returncode == 0 and default_viewer_status(mimes) == "default"
    if not done:  # no xdg-utils (or it wrote elsewhere): edit mimeapps.list directly
        parser = _read_mimeapps()
        if not parser.has_section("Default Applications"):
            parser.add_section("Default Applications")
        if not parser.has_section("Added Associations"):
            parser.add_section("Added Associations")
        for mime in mimes:
            parser.set("Default Applications", mime, DESKTOP_ID + ";")
            added = [a for a in parser.get("Added Associations", mime, fallback="").split(";") if a]
            if DESKTOP_ID not in added:
                parser.set("Added Associations", mime, ";".join([DESKTOP_ID] + added) + ";")
        path = _mimeapps_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".onegallery-tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            parser.write(f, space_around_delimiters=False)
        os.replace(tmp, path)
    for tool in ("kbuildsycoca6", "kbuildsycoca5"):  # let KDE notice right away
        if shutil.which(tool):
            subprocess.run([tool], capture_output=True, timeout=60)
            break
