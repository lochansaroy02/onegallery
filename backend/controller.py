"""Gallery controller: glue between settings, scanner, watcher, models and QML."""

import configparser
import logging
import os
import sys

from PySide6.QtCore import (
    Property, QFileSystemWatcher, QObject, QProcess, QProcessEnvironment, Qt, QTimer, QUrl,
    Signal, Slot,
)
from PySide6.QtGui import QGuiApplication, QPalette

from . import (
    PROJECT_URL, __version__, CACHE_DIR, CONFIG_PATH, DATA_DIR, DB_PATH, FFMPEG, HEIF_SUPPORTED, IS_WINDOWS, actions, desktop, printing, db, external, share, thumbs,
)
from .models import AlbumModel, PhotoModel, format_size
from .scanner import ScanThread, root_available
from .settings import Settings
from .tasks import run_async
from .watcher import FolderWatcher

log = logging.getLogger(__name__)

MOUNT_POLL_MS = 10_000
WATCH_DEBOUNCE_MS = 2_000
LIVE_RELOAD_MS = 4_000


def _kdeglobals_path() -> str:
    return os.path.join(
        os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"), "kdeglobals")


def _read_kdeglobals() -> configparser.RawConfigParser | None:
    parser = configparser.RawConfigParser(strict=False, interpolation=None)
    parser.optionxform = str
    try:
        return parser if parser.read(_kdeglobals_path(), encoding="utf-8") else None
    except (configparser.Error, UnicodeDecodeError):
        return None


def _rgb(value: str) -> tuple[int, int, int] | None:
    try:
        r, g, b = (int(x) for x in value.split(",")[:3])
    except (ValueError, AttributeError):
        return None
    return (r, g, b) if all(0 <= c <= 255 for c in (r, g, b)) else None


def _kde_prefers_dark() -> bool | None:
    parser = _read_kdeglobals()
    rgb = _rgb(parser.get("Colors:Window", "BackgroundNormal", fallback="")) if parser else None
    if rgb is None:
        return None
    r, g, b = rgb
    return (0.299 * r + 0.587 * g + 0.114 * b) < 128


def kde_accent_color() -> str:
    """KDE's accent colour as #rrggbb, or "" when it can't be read.

    System Settings > Colors & Themes > Colors > Accent color writes [General] AccentColor
    for both "From wallpaper" and a custom colour; "From current color scheme" leaves it
    out, and the scheme's own highlight colour is the accent."""
    parser = _read_kdeglobals()
    if parser is None:
        return ""
    for section, key in (("General", "AccentColor"), ("Colors:View", "DecorationFocus"),
                         ("Colors:Selection", "BackgroundNormal")):
        rgb = _rgb(parser.get(section, key, fallback=""))
        if rgb:
            return "#%02x%02x%02x" % rgb
    return ""


class Gallery(QObject):
    foldersChanged = Signal()
    scanningChanged = Signal()
    scanProgressChanged = Signal()
    systemDarkChanged = Signal()
    systemAccentChanged = Signal()
    cacheSizeChanged = Signal()
    toast = Signal(str)
    itemsRemoved = Signal()
    subfoldersLoaded = Signal(str, "QVariantList")  # folder, [{path, name, count, hasChildren}]
    externalOpenRequested = Signal(str)   # a file opened from Dolphin / the command line
    activateRequested = Signal()          # second launch without files: raise the window
    defaultViewerChanged = Signal()
    shareTargetsChanged = Signal()
    libraryReloaded = Signal()
    printersLoaded = Signal("QVariantMap")   # {printers: [...], paper: "a4"}
    frameCaptured = Signal(str)              # path of the saved video frame

    def __init__(self, settings: Settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        cols = settings.columns
        self.photos = PhotoModel(cols, "all", parent=self)
        self.albumPhotos = PhotoModel(cols, "none", auto_load=False, parent=self)
        self.searchPhotos = PhotoModel(cols, "none", auto_load=False, parent=self)
        self.videos = PhotoModel(cols, "videos", parent=self)
        self.albums = AlbumModel(settings, parent=self)
        self.externalPhotos = PhotoModel(cols, "none", auto_load=False, parent=self)
        self._grids = (self.photos, self.videos, self.albumPhotos, self.searchPhotos,
                       self.externalPhotos)
        self._default_viewer = ""
        self._share_available = share.available()
        self._share_cache: dict[str, list] = {}
        self._share_mime = ""
        self._share_targets: list = []
        self._share_loading = False
        self._share_procs: set = set()
        settings.columnsChanged.connect(self._sync_columns)
        settings.sortAscendingChanged.connect(self._sync_sort)
        self._sync_sort()

        self._folders: list[dict] = []
        self._availability: dict[str, bool] = {}
        self._scan: ScanThread | None = None
        self._pending_roots: set[str] | None = None  # None = nothing queued
        self._removals: list[str] = []
        self._found = 0
        self._scan_dir = ""
        self._cache_size = ""

        self._watcher = FolderWatcher(self)
        self._watch_changed: set[str] = set()
        self._watcher.rootChanged.connect(self._on_watch_event, Qt.QueuedConnection)
        self._watch_timer = QTimer(self, singleShot=True, interval=WATCH_DEBOUNCE_MS)
        self._watch_timer.timeout.connect(self._flush_watch_events)
        settings.liveUpdatesChanged.connect(self._update_watcher)

        self._mount_timer = QTimer(self, interval=MOUNT_POLL_MS)
        self._mount_timer.timeout.connect(self._poll_mounts)
        self._mount_timer.start()

        self._live_reload = QTimer(self, interval=LIVE_RELOAD_MS)
        self._live_reload.timeout.connect(self._reload_grids)

        self._system_dark = False
        self._system_accent = ""
        hints = QGuiApplication.styleHints()
        if hasattr(hints, "colorSchemeChanged"):
            hints.colorSchemeChanged.connect(self._update_system_theme)
        app = QGuiApplication.instance()
        if app is not None and hasattr(app, "paletteChanged"):
            app.paletteChanged.connect(self._update_system_theme)
        # KDE saves kdeglobals by replacing the file, which ends a plain file watch, so the
        # folder is watched too and the file is re-added after every change.
        self._kde_watch = QFileSystemWatcher(self)
        self._kde_watch.fileChanged.connect(self._on_kdeglobals_changed)
        self._kde_watch.directoryChanged.connect(self._on_kdeglobals_changed)
        self._theme_timer = QTimer(self, singleShot=True, interval=250)
        self._theme_timer.timeout.connect(self._update_system_theme)
        self._watch_kdeglobals()
        self._update_system_theme()

        self._refresh_folders()
        self._update_watcher()
        if self._folders:
            QTimer.singleShot(300, self.rescan)

    # ---- theme -----------------------------------------------------------------
    def _watch_kdeglobals(self):
        path = _kdeglobals_path()
        folder = os.path.dirname(path)
        if os.path.isdir(folder) and folder not in self._kde_watch.directories():
            self._kde_watch.addPath(folder)
        if os.path.exists(path) and path not in self._kde_watch.files():
            self._kde_watch.addPath(path)

    def _on_kdeglobals_changed(self, *_):
        self._watch_kdeglobals()
        self._theme_timer.start()  # coalesce the burst of events of one save

    def _update_system_theme(self, *_):
        self._update_system_dark()
        accent = kde_accent_color()
        if not accent:
            palette = QGuiApplication.palette()
            role = getattr(QPalette.ColorRole, "Accent", QPalette.ColorRole.Highlight)
            # Qt reads the desktop's accent colour on Linux, Windows and macOS
            accent = palette.color(role).name() if sys.platform in ("linux", "win32", "darwin") else ""
        if accent != self._system_accent:
            self._system_accent = accent
            self.systemAccentChanged.emit()

    @Property(str, notify=systemAccentChanged)
    def systemAccent(self):
        """The desktop's accent colour (#rrggbb), "" if unknown."""
        return self._system_accent

    def _update_system_dark(self, *_):
        dark = None
        hints = QGuiApplication.styleHints()
        if hasattr(hints, "colorScheme"):
            scheme = hints.colorScheme()
            if scheme == Qt.ColorScheme.Dark:
                dark = True
            elif scheme == Qt.ColorScheme.Light:
                dark = False
        if dark is None:
            dark = bool(_kde_prefers_dark())
        if dark != self._system_dark:
            self._system_dark = dark
            self.systemDarkChanged.emit()

    @Property(bool, notify=systemDarkChanged)
    def systemDark(self):
        return self._system_dark

    # ---- folders ------------------------------------------------------------------
    def _refresh_folders(self):
        entries = self.settings.folder_entries()
        self._availability = {e["path"]: root_available(e) for e in entries}
        self._folders = [
            {
                "path": e["path"],
                "name": os.path.basename(e["path"]) or e["path"],
                "mount": e.get("mount", "/"),
                "available": self._availability[e["path"]],
                "excludes": list(e.get("exclude", [])),
                "count": -1,
            }
            for e in entries
        ]
        self.foldersChanged.emit()
        run_async(db.root_counts, on_done=self._apply_counts)

    def _apply_counts(self, counts):
        for f in self._folders:
            f["count"] = counts.get(f["path"], 0)
        self.foldersChanged.emit()

    @Property("QVariantList", notify=foldersChanged)
    def folders(self):
        return self._folders

    @Property(bool, notify=foldersChanged)
    def hasFolders(self):
        return bool(self._folders)

    @Property(str, notify=foldersChanged)
    def suggestedFolder(self):
        pictures = os.path.expanduser("~/Pictures")
        if os.path.isdir(pictures) and pictures not in self.settings.folder_paths():
            return pictures
        return ""

    @Slot(str, result=str)
    def addFolder(self, folder):
        path = QUrl(folder).toLocalFile() if folder.startswith("file:") else folder
        error, replaced = self.settings.add_folder(path)
        if error:
            self.toast.emit(error)
            return error
        added = os.path.normpath(os.path.abspath(os.path.expanduser(path)))
        self._refresh_folders()
        self._update_watcher()
        self.rescan_roots({added})
        if replaced:
            self.toast.emit(f"Merged {len(replaced)} sub-folder(s) into {os.path.basename(added)}")
        return ""

    @Slot(str)
    def removeFolder(self, path):
        if not self.settings.remove_folder(path):
            return
        self._refresh_folders()
        self._update_watcher()
        if self._scan is not None:
            # stop the scan first so it cannot re-add rows for this folder;
            # the removal and a rescan of the remaining folders run when it ends
            self._removals.append(path)
            self._pending_roots = set(self.settings.folder_paths())
            self._scan.requestInterruption()
            return
        self._remove_rows(path)

    def _remove_rows(self, path):
        def done(count):
            self.toast.emit(f"Removed {count:,} item(s) from the gallery. Files were not touched.")
            self._reload_all()
            self._refresh_folders()

        run_async(db.remove_root, path, on_done=done)

    # ---- excluded sub-folders ----------------------------------------------------------------
    @Slot(str, "QStringList")
    def setExcludes(self, root, paths):
        before = set(self.settings.excludes(root))
        if not self.settings.set_excludes(root, list(paths)):
            return
        after = set(self.settings.excludes(root))
        self._refresh_folders()
        self._update_watcher()
        self.rescan_roots({root})
        added, removed = len(after - before), len(before - after)
        parts = []
        if added:
            parts.append(f"Excluded {added} folder{'s' if added != 1 else ''}: their pictures leave the "
                         "gallery (files are not touched)")
        if removed:
            parts.append(f"{removed} folder{'s' if removed != 1 else ''} included again")
        self.toast.emit(". ".join(parts) if parts else "Excluded folders updated")

    @Slot(str, str)
    def requestSubfolders(self, folder, root):
        """List folder's sub-folders with their indexed picture counts (async)."""
        def work(folder, root):
            from .scanner import should_skip_dir
            try:
                with os.scandir(folder) as it:
                    dirs = sorted((e for e in it if e.is_dir(follow_symlinks=False)
                                   and not should_skip_dir(e.name)), key=lambda e: e.name.casefold())
            except OSError:
                return []
            counts = {}
            for d, n in db.connect().execute(
                    "SELECT dir, COUNT(*) FROM images WHERE root = ? GROUP BY dir", (root,)):
                counts[d] = n
            result = []
            for e in dirs:
                prefix = e.path + os.sep
                total = sum(n for d, n in counts.items() if d == e.path or d.startswith(prefix))
                try:
                    with os.scandir(e.path) as it:
                        has_children = any(c.is_dir(follow_symlinks=False) and not should_skip_dir(c.name)
                                           for c in it)
                except OSError:
                    has_children = False
                result.append({"path": e.path, "name": e.name, "count": total,
                               "hasChildren": has_children})
            return result

        run_async(work, folder, root,
                  on_done=lambda items: self.subfoldersLoaded.emit(folder, items),
                  on_error=lambda _e: self.subfoldersLoaded.emit(folder, []))

    # ---- scanning --------------------------------------------------------------------
    @Slot()
    def rescan(self):
        self.rescan_roots(set(self.settings.folder_paths()))

    def rescan_roots(self, roots: set[str]):
        if not roots:
            return
        if self._scan is not None:
            self._pending_roots = (self._pending_roots or set()) | roots
            return
        entries = [e for e in self.settings.folder_entries() if e["path"] in roots]
        if not entries:
            return
        self._found = 0
        self._scan_dir = ""
        self._scan = ScanThread(entries, self.settings.minSizeKb)
        self._scan.progress.connect(self._on_progress)
        self._scan.scanFinished.connect(self._on_scan_finished)
        self._scan.finished.connect(self._scan.deleteLater)
        self._scan.start()
        self._live_reload.start()
        self.scanningChanged.emit()
        self.scanProgressChanged.emit()

    def _on_progress(self, found, directory):
        self._found = found
        self._scan_dir = directory
        self.scanProgressChanged.emit()

    def _on_scan_finished(self, stats):
        self._scan = None
        self._live_reload.stop()
        self.scanningChanged.emit()
        log.info("scan finished: %s", stats)
        removals, self._removals = self._removals, []
        for path in removals:
            self._remove_rows(path)
        self._reload_all()
        self._refresh_folders()
        for root in stats.get("unavailable", []):
            self.toast.emit(f"{os.path.basename(root) or root} is not available (drive unmounted?)")
        if self._pending_roots is not None:
            roots, self._pending_roots = self._pending_roots, None
            self.rescan_roots(roots & set(self.settings.folder_paths()))

    @Property(bool, notify=scanningChanged)
    def scanning(self):
        return self._scan is not None

    @Property(int, notify=scanProgressChanged)
    def scanFound(self):
        return self._found

    @Property(str, notify=scanProgressChanged)
    def scanDir(self):
        return self._scan_dir

    def _reload_grids(self):
        for m in self._grids:
            if m.filterKind != "none":
                m.reload()

    def _reload_all(self):
        self._reload_grids()
        self.albums.reload()
        self.libraryReloaded.emit()

    @Slot()
    def reloadLibrary(self):
        """Refresh every view after files were changed by the app (editor, trash)."""
        self._reload_all()
        self._refresh_folders()

    def _sync_sort(self):
        for m in (self.photos, self.videos, self.albumPhotos, self.searchPhotos):
            m.set_ascending(self.settings.sortAscending)

    def _sync_columns(self):
        for m in self._grids:
            m.columns = self.settings.columns

    # ---- live updates / mounts ----------------------------------------------------------
    def _update_watcher(self):
        if self.settings.liveUpdates:
            roots = [p for p, ok in self._availability.items() if ok]
            excludes = {e["path"]: e.get("exclude", []) for e in self.settings.folder_entries()}
            failed = self._watcher.watch(roots, excludes)
            if failed:
                self.toast.emit("Live updates unavailable for some folders (inotify limit?)")
        else:
            self._watcher.stop()

    def _on_watch_event(self, root):
        self._watch_changed.add(root)
        self._watch_timer.start()

    def _flush_watch_events(self):
        roots, self._watch_changed = self._watch_changed, set()
        self.rescan_roots(roots)

    def _poll_mounts(self):
        changed = set()
        for e in self.settings.folder_entries():
            ok = root_available(e)
            if self._availability.get(e["path"]) != ok:
                changed.add(e["path"])
        if changed:
            self._refresh_folders()
            self._update_watcher()
            self.rescan_roots(changed)

    @Property(bool, constant=True)
    def liveUpdatesSupported(self):
        return self._watcher.available

    @Property(bool, constant=True)
    def heifSupported(self):
        return HEIF_SUPPORTED

    @Property(bool, constant=True)
    def videoThumbnailsSupported(self):
        """ffmpeg is installed (video poster frames)."""
        return bool(FFMPEG)

    def shutdown(self):
        self._watcher.stop()
        if self._scan is not None:
            self._scan.requestInterruption()
            self._scan.wait(5000)

    # ---- actions ---------------------------------------------------------------------------
    @Slot("QVariantList", bool)
    def setFavorite(self, ids, value):
        ids = [int(i) for i in ids]

        def done(_):
            for m in self._grids:
                m.apply_favorite(ids, value)
            self.albums.reload()

        run_async(db.set_favorite, ids, value, on_done=done)

    @Slot("QStringList")
    def trash(self, paths):
        def work(paths):
            trashed, failed = actions.trash_files(paths)
            db.delete_paths(trashed)
            return trashed, failed

        def done(result):
            trashed, failed = result
            if failed:
                self.toast.emit(f"Could not move {len(failed)} item(s) to the trash")
            elif trashed:
                self.toast.emit(f"Moved {len(trashed)} item(s) to the trash")
            self._reload_all()
            self._refresh_folders()
            self.itemsRemoved.emit()

        run_async(work, list(paths), on_done=done)

    @Slot("QStringList")
    def copyPaths(self, paths):
        actions.copy_text("\n".join(paths))
        self.toast.emit("Path copied" if len(paths) == 1 else f"{len(paths)} paths copied")

    @Slot("QStringList")
    def shareFiles(self, paths):
        actions.copy_files(list(paths))
        self.toast.emit("Copied to clipboard. Paste into any app to share.")

    # ---- KDE share menu (Purpose) -------------------------------------------------------------
    @Slot("QStringList")
    def prepareShare(self, paths):
        """Load the share targets for these files (cached per MIME type)."""
        paths = [p for p in paths if p]
        if not paths:
            return
        mime = share.common_mime(paths)
        self._share_mime = mime
        if mime in self._share_cache:
            self._set_share_targets(self._share_cache[mime], False)
            return
        if not self._share_available:
            self._set_share_targets([], False)
            return
        self._set_share_targets([], True)

        def done(targets, mime=mime):
            self._share_cache[mime] = targets
            if self._share_mime == mime:
                self._set_share_targets(targets, False)

        run_async(share.list_targets, paths, mime, on_done=done,
                  on_error=lambda _exc: self._set_share_targets([], False))

    def _set_share_targets(self, targets, loading):
        self._share_targets = [t for t in targets if not share.is_clipboard(t.get("id", ""))]
        self._share_loading = loading
        self.shareTargetsChanged.emit()

    @Slot(str, "QStringList")
    def shareWith(self, plugin_id, paths):
        paths = [p for p in paths if p]
        if not paths:
            return
        if not plugin_id or share.is_clipboard(plugin_id) or not self._share_available:
            self.shareFiles(paths)
            return
        cmd = share.helper_command("run", share.common_mime(paths), plugin_id, paths)
        proc = QProcess(self)
        env = QProcessEnvironment()
        for key, value in share.helper_env().items():
            env.insert(key, value)
        proc.setProcessEnvironment(env)
        output = []
        proc.readyReadStandardError.connect(
            lambda: output.append(bytes(proc.readAllStandardError()).decode(errors="replace")))
        proc.readyReadStandardOutput.connect(
            lambda: output.append(bytes(proc.readAllStandardOutput()).decode(errors="replace")))

        def finished(code, _status):
            self._share_procs.discard(proc)
            proc.deleteLater()
            events = share.parse_events("".join(output))
            result = next((e for e in events if e.get("event") in ("finished", "cancelled")), None)
            if result is None:
                if code != 0:
                    log.warning("share helper exited with %s: %s", code, "".join(output)[-800:])
                    self.toast.emit("Sharing failed")
                return
            if result["event"] == "cancelled":
                return
            message, url = share.describe_result(result)
            if url:
                actions.copy_text(url)
            if message:
                self.toast.emit(message)

        proc.finished.connect(finished)
        proc.errorOccurred.connect(
            lambda err: err == QProcess.FailedToStart and self.toast.emit("Could not start the share helper"))
        self._share_procs.add(proc)
        proc.start(cmd[0], cmd[1:])

    @Property(bool, constant=True)
    def globalMenuAvailable(self):
        """True when a global menu is there: the Mac menu bar, or the KDE Global Menu widget
        listening on D-Bus."""
        if os.environ.get("ONEGALLERY_NO_GLOBAL_MENU"):
            return False
        if sys.platform == "darwin":
            return True
        if sys.platform != "linux":
            return False
        try:
            from PySide6.QtDBus import QDBusConnection
        except ImportError:
            return False
        bus = QDBusConnection.sessionBus()
        if not bus.isConnected():
            return False
        reply = bus.interface().isServiceRegistered("com.canonical.AppMenu.Registrar")
        return bool(reply.value()) if reply.isValid() else False

    @Property(bool, constant=True)
    def shareAvailable(self):
        return self._share_available

    @Property("QVariantList", notify=shareTargetsChanged)
    def shareTargets(self):
        return self._share_targets

    @Property(bool, notify=shareTargetsChanged)
    def shareLoading(self):
        return self._share_loading

    @Slot(str)
    def openExternally(self, path):
        if not actions.open_default(path):
            self.toast.emit("No application is set up to open this file")

    # ---- video frame capture --------------------------------------------------------------------
    @Slot(str, int)
    def captureFrame(self, path, ms):
        """Save the video frame at ms (full resolution) next to the video and add it to the library."""
        def work():
            from PySide6.QtCore import QStandardPaths

            from . import video
            from .scanner import UPSERT, read_metadata

            conn = db.connect()
            row = conn.execute("SELECT root, taken FROM images WHERE path = ?", (path,)).fetchone()
            taken = row[1] if row else None
            if taken is None:
                meta = video.probe(path)
                taken = meta.taken if meta and meta.taken else int(os.stat(path).st_mtime)
            folder = os.path.dirname(path)
            if not os.access(folder, os.W_OK):  # read-only drive: ~/Pictures/Screenshots
                pictures = QStandardPaths.writableLocation(QStandardPaths.PicturesLocation)
                folder = os.path.join(pictures or os.path.expanduser("~"), "Screenshots")
                os.makedirs(folder, exist_ok=True)
                row = None
            out = video.save_frame(path, ms, folder, taken)
            if row:  # same watched folder as the video: index it right away
                st = os.stat(out)
                meta = read_metadata(out, st.st_mtime)
                if meta:
                    with conn:
                        conn.execute(UPSERT, (out, row[0], folder, os.path.basename(out), meta.taken,
                                              st.st_mtime, st.st_size, meta.width, meta.height,
                                              None, None, 0, 0.0))
            return out

        def done(out):
            self.reloadLibrary()
            self.toast.emit(f"Frame saved to {os.path.basename(os.path.dirname(out))}")
            self.frameCaptured.emit(out)

        def failed(exc):
            log.warning("frame capture failed for %s: %s", path, exc)
            self.toast.emit(str(exc) or "Couldn't capture the frame")

        run_async(work, on_done=done, on_error=failed)

    # ---- set as wallpaper / lock screen, print ----------------------------------------------
    @Property(bool, constant=True)
    def wallpaperSupported(self):
        import shutil
        return bool(IS_WINDOWS or shutil.which("plasma-apply-wallpaperimage") or shutil.which("kwriteconfig6")
                    or shutil.which("kwriteconfig5") or shutil.which("gsettings")
                    or sys.platform == "darwin")

    @Slot(str, str)
    def setAsWallpaper(self, path, target):
        """target: "wallpaper", "lockscreen" or "both"."""
        messages = {"wallpaper": "Wallpaper set", "lockscreen": "Lock screen set",
                    "both": "Wallpaper and lock screen set"}

        def failed(exc):
            log.warning("set as %s failed: %s", target, exc)
            self.toast.emit(str(exc) or "Couldn't set the wallpaper")

        run_async(desktop.apply, path, target,
                  on_done=lambda t: self.toast.emit(messages.get(t, "Done")), on_error=failed)

    @Property(bool, constant=True)
    def printingSupported(self):
        return printing.AVAILABLE

    @Property("QVariantList", constant=True)
    def paperSizes(self):
        return printing.papers()

    @Slot()
    def requestPrinters(self):
        def work():
            return {"printers": printing.printers(), "paper": printing.default_paper()}

        run_async(work, on_done=self.printersLoaded.emit,
                  on_error=lambda exc: self.printersLoaded.emit(
                      {"printers": printing.printers(), "paper": "a4"}))

    @Slot(str, "QVariantMap")
    def printImage(self, path, options):
        opts = dict(options)

        def failed(exc):
            log.warning("printing %s failed: %s", path, exc)
            self.toast.emit(str(exc) or "Printing failed")

        self.toast.emit("Saving PDF…" if opts.get("printer") == printing.PDF else "Printing…")
        run_async(printing.print_image, path, opts, on_done=self.toast.emit, on_error=failed)

    @Slot(str, result=str)
    def pathToUrl(self, path):
        """file:// URL of a local path (file:///C:/... on Windows)."""
        return QUrl.fromLocalFile(path).toString()

    @Slot(str, result=str)
    def urlToPath(self, url):
        """Native local path of a file:// URL (C:\\... on Windows)."""
        return os.path.normpath(QUrl(url).toLocalFile()) if url.startswith("file:") else url

    @Slot(str, result=str)
    def defaultPdfPath(self, path):
        """~/Documents/<name>.pdf (or next to the picture when there is no Documents folder)."""
        from PySide6.QtCore import QStandardPaths
        docs = QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation)
        folder = docs if docs and os.path.isdir(docs) else os.path.dirname(path)
        base = os.path.splitext(os.path.basename(path))[0]
        out = os.path.join(folder, base + ".pdf")
        n = 2
        while os.path.exists(out):
            out = os.path.join(folder, f"{base} ({n}).pdf")
            n += 1
        return out

    @Slot(str)
    def showInFolder(self, path):
        def done(ok):
            if not ok:
                actions.open_folder(path)

        run_async(actions.show_in_folder_blocking, path, on_done=done,
                  on_error=lambda _e: actions.open_folder(path))

    @Slot(str, result="QVariantList")
    def appsFor(self, path):
        try:
            return actions.apps_for_file(path)
        except Exception as exc:
            log.warning("listing applications failed: %s", exc)
            return []

    @Slot(str, "QStringList")
    def openWith(self, desktop_file, paths):
        if not actions.launch_desktop_app(desktop_file, list(paths)):
            self.toast.emit("Could not start the application")

    # ---- opening files from outside ----------------------------------------------------------
    @Slot("QStringList")
    def openFiles(self, args):
        """Open pictures given on the command line / by the file manager, without indexing them."""
        files = external.paths_from_args(list(args))
        if not files:
            self.activateRequested.emit()
            return
        focus = files[0]
        self.settings.add_recent(files)
        self.externalPhotos.openExternal(focus, files if len(files) > 1 else [])
        self.externalOpenRequested.emit(focus)

    def _viewer_mimes(self):
        return actions.VIEWER_MIMES + (actions.HEIF_MIMES if HEIF_SUPPORTED else [])

    @Slot()
    def refreshDefaultViewer(self):
        def done(status):
            self._default_viewer = status
            self.defaultViewerChanged.emit()

        run_async(actions.default_viewer_status, self._viewer_mimes(), on_done=done)

    @Property(bool, constant=True)
    def isWindows(self):
        return IS_WINDOWS

    @Property(bool, constant=True)
    def isMac(self):
        return sys.platform == "darwin"

    @Property(bool, constant=True)
    def lockScreenSupported(self):
        """macOS shows the desktop picture on the lock screen: there is no separate one."""
        return sys.platform != "darwin"

    @Slot(str)
    def openWithDialog(self, path):
        """The system's own "Open with" chooser (Windows)."""
        if not actions.windows_open_with(path):
            self.toast.emit("Couldn't open the Open with dialog")

    @Slot()
    def setAsDefaultViewer(self):
        if IS_WINDOWS:  # Windows lets only the user choose: open Settings > Default apps
            if not actions.windows_default_apps():
                self.toast.emit("Open Settings > Apps > Default apps and choose One Gallery")
            return
        def done(_):
            self.toast.emit("One Gallery is now your default image viewer")
            self.refreshDefaultViewer()

        def failed(exc):
            self.toast.emit(str(exc) if isinstance(exc, RuntimeError) else f"Could not set default: {exc}")
            self.refreshDefaultViewer()

        run_async(actions.set_default_viewer, self._viewer_mimes(), on_done=done, on_error=failed)

    @Property(str, notify=defaultViewerChanged)
    def defaultViewer(self):
        return self._default_viewer

    # ---- cache / info --------------------------------------------------------------------
    @Slot()
    def refreshCacheSize(self):
        def done(size):
            self._cache_size = format_size(size)
            self.cacheSizeChanged.emit()

        run_async(thumbs.cache_size, on_done=done)

    @Slot()
    def clearThumbnailCache(self):
        def done(_):
            self.toast.emit("Thumbnail cache cleared")
            self.refreshCacheSize()

        run_async(thumbs.clear_cache, on_done=done)

    @Property(str, notify=cacheSizeChanged)
    def cacheSize(self):
        return self._cache_size

    @Property(str, constant=True)
    def version(self):
        return __version__

    @Property(str, constant=True)
    def projectUrl(self):
        return PROJECT_URL

    @Property("QVariantMap", constant=True)
    def locations(self):
        return {"config": str(CONFIG_PATH), "index": str(DB_PATH), "cache": str(CACHE_DIR),
                "originals": str(DATA_DIR / "originals")}
