"""Watched folders and preferences, persisted to ~/.config/onegallery/config.json."""

import json
import logging
import os
import re

from PySide6.QtCore import Property, QObject, Signal, Slot

from . import CONFIG_PATH

log = logging.getLogger(__name__)

DEFAULTS = {
    "folders": [],            # [{"path": "/abs/path", "mount": "/mount/point", "exclude": [...]}]
    "theme": "system",        # system | light | dark
    "accent": "system",       # system (KDE accent colour) | "#rrggbb"
    "color_style": "neutral", # neutral (black & white) | tinted (Material You, from the accent)
    "nav_style": "solid",     # solid | frosted | clear (Liquid Glass navigation bar)
    "min_size_kb": 20,
    "columns": 6,
    "albums_by_subfolder": False,
    "live_updates": True,
    "sort_ascending": False,  # False = newest first
    "recent_files": [],       # pictures opened from outside the library
    "faces_enabled": False,   # People: on-device face grouping (opt-in)
}
MAX_RECENT = 10

MIN_COLUMNS, MAX_COLUMNS = 2, 12


def mount_point(path: str) -> str:
    """The mount point containing path (works for paths that no longer exist)."""
    path = os.path.realpath(path)
    while not os.path.ismount(path):
        parent = os.path.dirname(path)
        if parent == path:
            break
        path = parent
    return path


def _is_within(child: str, parent: str) -> bool:
    return child == parent or child.startswith(parent.rstrip(os.sep) + os.sep)


class Settings(QObject):
    foldersChanged = Signal()
    themeChanged = Signal()
    accentChanged = Signal()
    colorStyleChanged = Signal()
    navStyleChanged = Signal()
    minSizeKbChanged = Signal()
    columnsChanged = Signal()
    albumsBySubfolderChanged = Signal()
    liveUpdatesChanged = Signal()
    sortAscendingChanged = Signal()
    recentFilesChanged = Signal()
    facesEnabledChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data = dict(DEFAULTS)
        self._load()

    # ---- persistence -------------------------------------------------
    def _load(self):
        try:
            with open(CONFIG_PATH, encoding="utf-8") as f:
                stored = json.load(f)
            if isinstance(stored, dict):
                self._data.update({k: v for k, v in stored.items() if k in DEFAULTS})
        except FileNotFoundError:
            pass
        except (OSError, ValueError) as exc:
            log.warning("could not read %s: %s (using defaults)", CONFIG_PATH, exc)
        self._data["folders"] = [
            f for f in self._data.get("folders", []) if isinstance(f, dict) and f.get("path")
        ]

    def save(self):
        try:
            CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            tmp = CONFIG_PATH.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2)
            os.replace(tmp, CONFIG_PATH)
        except OSError as exc:
            log.error("could not save settings: %s", exc)

    def _set(self, key, value, signal):
        if self._data.get(key) != value:
            self._data[key] = value
            self.save()
            signal.emit()

    # ---- folders -----------------------------------------------------
    def folder_entries(self) -> list[dict]:
        return [dict(f) for f in self._data["folders"]]

    def folder_paths(self) -> list[str]:
        return [f["path"] for f in self._data["folders"]]

    def add_folder(self, path: str) -> tuple[str, list[str]]:
        """Add a folder. Returns (error_message, replaced_child_paths)."""
        path = os.path.normpath(os.path.abspath(os.path.expanduser(path)))
        if not os.path.isdir(path):
            return f"{path} is not a folder", []
        for entry in self._data["folders"]:
            existing = entry["path"]
            # a folder inside an excluded sub-folder of another watched folder is allowed
            if _is_within(path, existing) and not any(
                    _is_within(path, ex) for ex in entry.get("exclude", [])):
                return f"Already included in {existing}", []
        children = [p for p in self.folder_paths() if _is_within(p, path)]
        folders = [f for f in self._data["folders"] if f["path"] not in children]
        folders.append({"path": path, "mount": mount_point(path)})
        self._data["folders"] = folders
        self.save()
        self.foldersChanged.emit()
        return "", children

    def excludes(self, root: str) -> list[str]:
        for f in self._data["folders"]:
            if f["path"] == root:
                return list(f.get("exclude", []))
        return []

    def set_excludes(self, root: str, paths: list[str]) -> bool:
        """Sub-folders of root that are not scanned. Nested entries are collapsed."""
        clean = []
        for p in sorted({os.path.normpath(p) for p in paths if p}):
            if _is_within(p, root) and p != root and not any(_is_within(p, c) for c in clean):
                clean.append(p)
        for f in self._data["folders"]:
            if f["path"] == root:
                if f.get("exclude", []) == clean:
                    return False
                f["exclude"] = clean
                self.save()
                self.foldersChanged.emit()
                return True
        return False

    def remove_folder(self, path: str) -> bool:
        folders = [f for f in self._data["folders"] if f["path"] != path]
        if len(folders) == len(self._data["folders"]):
            return False
        self._data["folders"] = folders
        self.save()
        self.foldersChanged.emit()
        return True

    # ---- preferences exposed to QML ------------------------------------
    def _get_theme(self):
        return self._data["theme"]

    def _set_theme(self, value):
        if value in ("system", "light", "dark"):
            self._set("theme", value, self.themeChanged)

    theme = Property(str, _get_theme, _set_theme, notify=themeChanged)

    def _get_accent(self):
        return self._data.get("accent", "system")

    def _set_accent(self, value):
        value = str(value).strip().lower()
        if value != "system" and not re.fullmatch(r"#[0-9a-f]{6}", value):
            return
        self._set("accent", value, self.accentChanged)

    accent = Property(str, _get_accent, _set_accent, notify=accentChanged)

    def _get_color_style(self):
        value = self._data.get("color_style", "neutral")
        return value if value in ("neutral", "tinted") else "neutral"

    def _set_color_style(self, value):
        if value in ("neutral", "tinted"):
            self._set("color_style", value, self.colorStyleChanged)

    colorStyle = Property(str, _get_color_style, _set_color_style, notify=colorStyleChanged)

    def _get_nav_style(self):
        value = self._data.get("nav_style", "solid")
        return value if value in ("solid", "frosted", "clear") else "solid"

    def _set_nav_style(self, value):
        if value in ("solid", "frosted", "clear"):
            self._set("nav_style", value, self.navStyleChanged)

    navStyle = Property(str, _get_nav_style, _set_nav_style, notify=navStyleChanged)

    def _get_min_size(self):
        return int(self._data["min_size_kb"])

    def _set_min_size(self, value):
        self._set("min_size_kb", max(0, int(value)), self.minSizeKbChanged)

    minSizeKb = Property(int, _get_min_size, _set_min_size, notify=minSizeKbChanged)

    def _get_columns(self):
        return int(self._data["columns"])

    def _set_columns(self, value):
        value = max(MIN_COLUMNS, min(MAX_COLUMNS, int(value)))
        self._set("columns", value, self.columnsChanged)

    columns = Property(int, _get_columns, _set_columns, notify=columnsChanged)

    def _get_by_sub(self):
        return bool(self._data["albums_by_subfolder"])

    def _set_by_sub(self, value):
        self._set("albums_by_subfolder", bool(value), self.albumsBySubfolderChanged)

    albumsBySubfolder = Property(
        bool, _get_by_sub, _set_by_sub, notify=albumsBySubfolderChanged
    )

    def _get_live(self):
        return bool(self._data["live_updates"])

    def _set_live(self, value):
        self._set("live_updates", bool(value), self.liveUpdatesChanged)

    liveUpdates = Property(bool, _get_live, _set_live, notify=liveUpdatesChanged)

    def _get_sort(self):
        return bool(self._data["sort_ascending"])

    def _set_sort(self, value):
        self._set("sort_ascending", bool(value), self.sortAscendingChanged)

    sortAscending = Property(bool, _get_sort, _set_sort, notify=sortAscendingChanged)

    def _get_faces(self):
        return bool(self._data["faces_enabled"])

    def _set_faces(self, value):
        self._set("faces_enabled", bool(value), self.facesEnabledChanged)

    facesEnabled = Property(bool, _get_faces, _set_faces, notify=facesEnabledChanged)

    @Property("QStringList", notify=recentFilesChanged)
    def recentFiles(self):
        return [p for p in self._data.get("recent_files", []) if isinstance(p, str)]

    def add_recent(self, paths: list[str]):
        recent = [p for p in paths if p] + [p for p in self.recentFiles if p not in paths]
        self._set("recent_files", recent[:MAX_RECENT], self.recentFilesChanged)

    def remove_recent(self, paths):
        gone = set(paths)
        recent = [p for p in self.recentFiles if p not in gone]
        if len(recent) != len(self.recentFiles):
            self._set("recent_files", recent, self.recentFilesChanged)

    @Slot()
    def clearRecent(self):
        self._set("recent_files", [], self.recentFilesChanged)

    @Property(int, constant=True)
    def minColumns(self):
        return MIN_COLUMNS

    @Property(int, constant=True)
    def maxColumns(self):
        return MAX_COLUMNS
