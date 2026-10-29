"""One Gallery backend: index, scanner, thumbnails, models and actions."""

__version__ = "0.4.0"
PROJECT_URL = "https://github.com/lochansaroy02/onegallery"

import os
import shutil
import sys
from pathlib import Path

IS_WINDOWS = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")
# folder of the bundled app (PyInstaller sets sys.frozen / sys._MEIPASS)
APP_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))


def _xdg(var: str, fallback: str) -> Path:
    value = os.environ.get(var)
    return Path(value) if value else Path.home() / fallback


# ONEGALLERY_HOME redirects every location (used by the tests and sample runs).
_home = os.environ.get("ONEGALLERY_HOME")
if _home:
    CONFIG_DIR = Path(_home) / "config"
    DATA_DIR = Path(_home) / "data"
    CACHE_DIR = Path(_home) / "cache"
elif IS_WINDOWS:  # %APPDATA%\OneGallery (settings), %LOCALAPPDATA%\OneGallery (index, cache)
    _roaming = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    _local = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    CONFIG_DIR = _roaming / "OneGallery"
    DATA_DIR = _local / "OneGallery"
    CACHE_DIR = _local / "OneGallery" / "cache"
elif IS_MAC:  # ~/Library/Application Support/One Gallery (settings, index), ~/Library/Caches
    CONFIG_DIR = Path.home() / "Library" / "Application Support" / "One Gallery"
    DATA_DIR = CONFIG_DIR
    CACHE_DIR = Path.home() / "Library" / "Caches" / "One Gallery"
else:
    CONFIG_DIR = _xdg("XDG_CONFIG_HOME", ".config") / "onegallery"
    DATA_DIR = _xdg("XDG_DATA_HOME", ".local/share") / "onegallery"
    CACHE_DIR = _xdg("XDG_CACHE_HOME", ".cache") / "onegallery"


def migrate_old_name() -> list[str]:
    """The app used to be called LGallery. Move its settings, library and cache to the new
    folders the first time One Gallery starts, and point mimeapps.list at the new launcher.

    On a Mac the folders also move out of the Linux-style ~/.config, ~/.local/share and
    ~/.cache (where running from source used to put them) into ~/Library.

    Outside Windows the old folder names are left as links to the new ones, so anything
    outside the app that remembers a path inside them (the wallpaper, for one) keeps working.
    Returns what was done, for the log."""
    if _home:
        return []
    config, data, cache = (_xdg("XDG_CONFIG_HOME", ".config"), _xdg("XDG_DATA_HOME", ".local/share"),
                           _xdg("XDG_CACHE_HOME", ".cache"))
    merge = []  # (new folder, old folders): files copied in one by one (the Mac's shared folder)
    if IS_WINDOWS:
        old = {CONFIG_DIR: [_roaming / "LGallery"], DATA_DIR: [_local / "LGallery"]}  # cache is inside DATA_DIR
    elif IS_MAC:
        old = {DATA_DIR: [data / "onegallery", data / "lgallery"],
               CACHE_DIR: [cache / "onegallery", cache / "lgallery"]}
        merge = [(CONFIG_DIR, [config / "onegallery", config / "lgallery"])]
    else:
        old = {CONFIG_DIR: [config / "lgallery"], DATA_DIR: [data / "lgallery"], CACHE_DIR: [cache / "lgallery"]}
    done = []
    for new, candidates in old.items():
        before = next((c for c in candidates if c.is_dir() and not c.is_symlink()), None)
        if new.exists() or before is None:
            continue
        try:
            new.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(before), str(new))
        except OSError as exc:  # leave it where it is: the old data stays safe
            done.append(f"could not move {before} to {new}: {exc}")
            continue
        done.append(f"moved {before} to {new}")
        if not IS_WINDOWS:
            try:
                before.symlink_to(new, target_is_directory=True)
            except OSError:
                pass
    for new, candidates in merge:
        before = next((c for c in candidates if c.is_dir() and not c.is_symlink()), None)
        if before is None:
            continue
        new.mkdir(parents=True, exist_ok=True)
        moved = 0
        for item in before.iterdir():
            if not (new / item.name).exists():
                try:
                    shutil.move(str(item), str(new / item.name))
                    moved += 1
                except OSError as exc:
                    done.append(f"could not move {item} to {new}: {exc}")
        if moved:
            done.append(f"moved the settings in {before} to {new}")
    if IS_LINUX:
        done += _migrate_mimeapps()
    return done


def _migrate_mimeapps() -> list[str]:
    """lgallery.desktop -> onegallery.desktop in ~/.config/mimeapps.list, once the new
    launcher is installed (otherwise pictures would open in nothing)."""
    import re
    path = _xdg("XDG_CONFIG_HOME", ".config") / "mimeapps.list"
    dirs = [_xdg("XDG_DATA_HOME", ".local/share")] + [
        Path(d) for d in (os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share").split(":") if d]
    if not any((d / "applications" / "onegallery.desktop").exists() for d in dirs):
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    new = re.sub(r"(?<![\w.-])lgallery\.desktop", "onegallery.desktop", text)
    if new == text:
        return []
    try:
        tmp = path.with_name(path.name + ".onegallery-tmp")
        tmp.write_text(new, encoding="utf-8")
        os.replace(tmp, path)
    except OSError as exc:
        return [f"could not update {path}: {exc}"]
    return [f"pointed {path} at onegallery.desktop"]


DB_PATH = DATA_DIR / "index.db"
CONFIG_PATH = CONFIG_DIR / "config.json"
THUMB_DIR = CACHE_DIR / "thumbs"

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff"}
HEIF_EXTS = {".heic", ".heif"}
VIDEO_EXTS = {".mp4", ".m4v", ".mov", ".mkv", ".webm", ".avi", ".3gp", ".mts", ".m2ts",
              ".wmv", ".ogv", ".mpg", ".mpeg"}

# Video posters, thumbnails and metadata come from the system ffmpeg when it is installed
# (sudo pacman -S ffmpeg). Without it MP4/MOV dates still come from the file itself.
def _find_tool(name: str) -> str | None:
    """A copy bundled with the app (the Windows and Mac builds have an ffmpeg folder) first."""
    for folder in (APP_DIR / "ffmpeg", APP_DIR):
        for candidate in (folder / f"{name}.exe", folder / name):
            if candidate.is_file():
                return str(candidate)
    found = shutil.which(name)
    if not found and IS_MAC:  # an app started from Finder doesn't have Homebrew on its PATH
        found = next((str(p) for p in (Path("/opt/homebrew/bin") / name, Path("/usr/local/bin") / name)
                      if p.is_file()), None)
    return found


# keyword arguments for subprocess calls: no console window flashing up on Windows
NO_WINDOW = {"creationflags": 0x08000000} if IS_WINDOWS else {}  # CREATE_NO_WINDOW

FFMPEG = _find_tool("ffmpeg")
FFPROBE = _find_tool("ffprobe")

try:
    from pillow_heif import register_heif_opener

    register_heif_opener()
    HEIF_SUPPORTED = True
except Exception:  # not installed or broken libheif
    HEIF_SUPPORTED = False


def supported_exts() -> set[str]:
    images = IMAGE_EXTS | HEIF_EXTS if HEIF_SUPPORTED else IMAGE_EXTS
    return images | VIDEO_EXTS


def is_video(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in VIDEO_EXTS
