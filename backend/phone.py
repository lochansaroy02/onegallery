"""Phone sync: import new photos and videos from phones paired with KDE Connect.

KDE Connect's "Browse device" (SFTP) plugin mounts the phone's storage over Wi-Fi with
sshfs. One Gallery asks kdeconnectd over D-Bus to mount it (with busctl, which prints
typed JSON), copies new files from the camera folders (DCIM) and, if wanted, the
screenshot folders to ~/Pictures/Phone/<phone>/, and unmounts the phone again if it
wasn't mounted before. Every imported file is recorded in phone_imports, so a picture
deleted on the computer is not imported again.

Exposed to QML as `phones`.
"""

import json
import logging
import os
import shutil
import subprocess
import sys
import time
from typing import NamedTuple

from PySide6.QtCore import Property, QObject, QStandardPaths, QTimer, Signal, Slot

from . import HEIF_EXTS, IMAGE_EXTS, VIDEO_EXTS, actions, db
from .tasks import run_async

log = logging.getLogger(__name__)

SERVICE = "org.kde.kdeconnect"
DAEMON_PATH = "/modules/kdeconnect"
DEVICE_IFACE = "org.kde.kdeconnect.device"
SFTP_IFACE = "org.kde.kdeconnect.device.sftp"
SFTP_PLUGIN = "kdeconnect_sftp"
PHONE_TYPES = ("phone", "smartphone", "tablet")

MEDIA_EXTS = IMAGE_EXTS | HEIF_EXTS | VIDEO_EXTS | {".dng"}
SCREENSHOT_DIRS = ("DCIM/Screenshots", "Pictures/Screenshots")
STORAGE_SEARCH_DEPTH = 3     # mount point -> storage/emulated/0 -> DCIM
POLL_MS = 30_000             # look for phones this often
AUTO_SYNC_EVERY = 10 * 60    # seconds between automatic syncs of a connected phone
MAX_FAILURES = 5             # consecutive copy errors before giving up (phone went away)


class BusError(RuntimeError):
    pass


class SyncError(RuntimeError):
    expected = True   # shown as a message, logged without a traceback


def supported() -> bool:
    return sys.platform.startswith("linux") and shutil.which("busctl") is not None


def _busctl(args: list[str], timeout: float = 30) -> str:
    try:
        result = subprocess.run(["busctl", "--user", "--json=short", f"--timeout={int(timeout)}", *args],
                                capture_output=True, text=True, timeout=timeout + 5)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise BusError(str(exc)) from exc
    if result.returncode != 0:
        raise BusError(result.stderr.strip() or f"busctl exited with {result.returncode}")
    return result.stdout


def _arg(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _plain(value):
    """busctl's {"type": ..., "data": ...} variants -> plain Python values."""
    if isinstance(value, dict) and set(value) == {"type", "data"}:
        return _plain(value["data"])
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_plain(v) for v in value]
    return value


def _as_dict(value) -> dict:
    """a{sv} as busctl prints it: a JSON object (or, to be safe, a list of key/value pairs)."""
    if isinstance(value, dict):
        return value
    if isinstance(value, list) and all(isinstance(p, list) and len(p) == 2 for p in value):
        return {k: v for k, v in value}
    return {}


class KdeConnect:
    """The few kdeconnectd D-Bus calls phone sync needs. `run` is busctl (replaceable in tests)."""

    def __init__(self, run=None):
        self._run = run or _busctl

    def _call(self, path, iface, method, signature="", *args, timeout=30):
        cmd = ["call", SERVICE, path, iface, method]
        if signature:
            cmd += [signature, *(_arg(a) for a in args)]
        out = self._run(cmd, timeout)
        if not out.strip():
            return None
        data = json.loads(out).get("data", [])
        return _plain(data[0]) if data else None

    def device_ids(self) -> list[str]:
        """Paired devices, reachable or not."""
        return list(self._call(DAEMON_PATH, "org.kde.kdeconnect.daemon", "devices", "bb", False, True) or [])

    def device(self, device_id: str) -> dict:
        path = f"{DAEMON_PATH}/devices/{device_id}"
        props = _as_dict(self._call(path, "org.freedesktop.DBus.Properties", "GetAll", "s", DEVICE_IFACE))
        try:
            plugins = self._call(path, DEVICE_IFACE, "loadedPlugins") or []
        except (BusError, ValueError):
            plugins = None   # older kdeconnectd: find out when mounting
        return {
            "id": device_id,
            "name": props.get("name") or device_id,
            "type": props.get("type", ""),
            "reachable": bool(props.get("isReachable")),
            "browsable": plugins is None or SFTP_PLUGIN in plugins,
        }

    def running(self) -> bool:
        """kdeconnectd is running (asked without calling it, which would start it)."""
        out = self._run(["call", "org.freedesktop.DBus", "/org/freedesktop/DBus",
                         "org.freedesktop.DBus", "NameHasOwner", "s", SERVICE], 30)
        data = json.loads(out).get("data", [False]) if out.strip() else [False]
        return bool(data and data[0])

    def phones(self) -> list[dict] | None:
        """Paired phones, or None when KDE Connect isn't running or can't be reached."""
        try:
            if not self.running():
                return None
            return [d for d in (self.device(i) for i in self.device_ids())
                    if d["type"] in PHONE_TYPES or d["type"] == ""]
        except (BusError, ValueError) as exc:
            log.debug("phone: KDE Connect not reachable: %s", exc)
            return None

    def _sftp(self, device_id, method, signature="", *args, timeout=30):
        return self._call(f"{DAEMON_PATH}/devices/{device_id}/sftp", SFTP_IFACE, method,
                          signature, *args, timeout=timeout)

    def is_mounted(self, device_id: str) -> bool:
        return bool(self._sftp(device_id, "isMounted"))

    def mount(self, device_id: str) -> None:
        if not self._sftp(device_id, "mountAndWait", timeout=90):
            try:
                reason = self._sftp(device_id, "getMountError") or ""
            except BusError:
                reason = ""
            raise SyncError(f"Could not open the phone's storage{': ' + reason if reason else ''}")

    def unmount(self, device_id: str) -> None:
        self._sftp(device_id, "unmount")

    def storage_dirs(self, device_id: str) -> list[str]:
        """The mount point and the folders KDE Connect offers ("All files", "Camera pictures")."""
        dirs = [self._sftp(device_id, "mountPoint") or ""]
        try:
            dirs += list(_as_dict(self._sftp(device_id, "getDirectories")).keys())
        except BusError:
            pass
        return [d for d in dirs if d]


# ---- finding and copying files (no D-Bus: works on any folder, see tests) ---------------------
class Item(NamedTuple):
    src: str        # file on the phone (in the mount)
    key: str        # stable id on the phone: path below its storage root, with the root's name
    dest_rel: str   # where it goes below ~/Pictures/Phone/<phone>/
    size: int
    mtime: float


def _hidden(name: str) -> bool:
    # .thumbnails, Android's .trashed-<time>-name.jpg and .pending-<time>-name.jpg
    return name.startswith(".")


def find_storage_roots(dirs: list[str], depth: int = STORAGE_SEARCH_DEPTH) -> list[str]:
    """Folders that contain a DCIM folder (internal storage, SD card), searched from dirs."""
    roots, seen = [], set()

    def visit(path, level):
        real = os.path.realpath(path)
        if real in seen:
            return
        seen.add(real)
        try:
            entries = [e for e in os.scandir(path) if not _hidden(e.name) and e.is_dir()]
        except OSError:
            return
        if any(e.name == "DCIM" for e in entries):
            roots.append(path)
            return
        if level < depth:
            for e in entries:
                visit(e.path, level + 1)

    for d in dirs:
        if os.path.isdir(d):
            # a folder KDE Connect offers may itself be inside a storage root (.../DCIM/Camera)
            parts = os.path.normpath(d).split(os.sep)
            if "DCIM" in parts:
                d = os.sep.join(parts[:parts.index("DCIM")]) or os.sep
            visit(d, 0)
    return roots


def _walk_media(top: str):
    try:
        entries = list(os.scandir(top))
    except OSError as exc:
        log.info("phone: cannot read %s: %s", top, exc)
        return
    for e in entries:
        if _hidden(e.name):
            continue
        try:
            if e.is_dir():
                yield from _walk_media(e.path)
            elif os.path.splitext(e.name)[1].lower() in MEDIA_EXTS:
                st = e.stat()
                if st.st_size > 0:
                    yield e.path, st
        except OSError:
            continue


def find_media(roots: list[str], screenshots: bool) -> list[Item]:
    """Photos and videos in the camera folders (everything in DCIM) and, if wanted, in the
    screenshot folders. Destination: the folder below DCIM or Pictures (Camera, Screenshots)."""
    items, seen = [], set()
    for root in roots:
        label = os.path.basename(root.rstrip(os.sep)) or "storage"
        tops = [(os.path.join(root, "DCIM"), os.path.join(root, "DCIM"))]
        if screenshots:
            tops += [(os.path.join(root, d), os.path.dirname(os.path.join(root, d))) for d in SCREENSHOT_DIRS]
        for top, base in tops:
            for path, st in _walk_media(top):
                rel = os.path.relpath(path, base)
                if not screenshots and rel.split(os.sep)[0] == "Screenshots":
                    continue
                key = f"{label}/{os.path.relpath(path, root)}"
                if key in seen:
                    continue
                seen.add(key)
                items.append(Item(path, key, rel, st.st_size, st.st_mtime))
    items.sort(key=lambda i: i.mtime)
    return items


def imported_keys(device_id: str) -> set[str]:
    rows = db.connect().execute("SELECT key FROM phone_imports WHERE device = ?", (device_id,))
    return {r[0] for r in rows}


def _record(device_id: str, items: list[Item]) -> None:
    conn = db.connect()
    with conn:
        conn.executemany(
            "INSERT OR REPLACE INTO phone_imports (device, key, size, mtime, imported) VALUES (?, ?, ?, ?, ?)",
            [(device_id, i.key, i.size, int(i.mtime), int(time.time())) for i in items])


def forget_device(device_id: str) -> None:
    conn = db.connect()
    with conn:
        conn.execute("DELETE FROM phone_imports WHERE device = ?", (device_id,))


def _free_name(path: str) -> str:
    stem, ext = os.path.splitext(path)
    n = 1
    while os.path.exists(path):
        path = f"{stem} ({n}){ext}"
        n += 1
    return path


def copy_item(item: Item, dest_dir: str) -> str | None:
    """Copy one file; returns the new path, or None when the same file is already there."""
    dest = os.path.join(dest_dir, item.dest_rel)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    if os.path.exists(dest):
        if os.path.getsize(dest) == item.size:
            return None
        dest = _free_name(dest)
    # copied under a hidden name first: the scanner and live updates never see half a file
    part = os.path.join(os.path.dirname(dest), f".{os.path.basename(dest)}.onegallery-part")
    try:
        shutil.copyfile(item.src, part)
        os.utime(part, (item.mtime, item.mtime))
        os.replace(part, dest)
    except BaseException:
        try:
            os.unlink(part)
        except OSError:
            pass
        raise
    return dest


def import_new(device_id: str, dest_dir: str, items: list[Item], progress=None,
               cancelled=lambda: False) -> dict:
    """Copy the items not imported before. Returns {imported, skipped, failed, cancelled}."""
    known = imported_keys(device_id)
    todo = [i for i in items if i.key not in known]
    stats = {"imported": 0, "skipped": len(items) - len(todo), "failed": 0, "cancelled": False}
    done, failures = [], 0
    for n, item in enumerate(todo):
        if cancelled():
            stats["cancelled"] = True
            break
        if progress:
            progress(n, len(todo))
        try:
            copied = copy_item(item, dest_dir)
        except OSError as exc:
            log.warning("phone: could not copy %s: %s", item.src, exc)
            stats["failed"] += 1
            failures += 1
            if failures >= MAX_FAILURES:
                _record(device_id, done)
                raise SyncError("The phone stopped responding. Check that it's still connected.") from exc
            continue
        failures = 0
        stats["imported" if copied else "skipped"] += 1
        done.append(item)
        if len(done) >= 50:
            _record(device_id, done)
            done = []
    _record(device_id, done)
    if progress:
        progress(len(todo), len(todo))
    return stats


def safe_folder_name(name: str) -> str:
    clean = "".join("_" if c in '/\\:*?"<>|' or ord(c) < 32 else c for c in name).strip(" .")
    return clean or "Phone"


def phone_base_dir() -> str:
    pictures = QStandardPaths.writableLocation(QStandardPaths.PicturesLocation) or os.path.expanduser("~/Pictures")
    return os.path.join(pictures, "Phone")


def sync_device(bus: KdeConnect, device_id: str, dest_dir: str, mode: str, screenshots: bool,
                progress=None, cancelled=lambda: False) -> dict:
    """Mount the phone, then import new files (mode "all") or only remember what's there
    now, so that later syncs bring just the newer ones (mode "new")."""
    was_mounted = bus.is_mounted(device_id)
    if not was_mounted:
        bus.mount(device_id)
    try:
        roots = find_storage_roots(bus.storage_dirs(device_id))
        if not roots:
            raise SyncError("No camera folder (DCIM) found on the phone")
        items = find_media(roots, screenshots)
        if mode == "new":
            _record(device_id, [i for i in items if i.key not in imported_keys(device_id)])
            stats = {"imported": 0, "skipped": len(items), "failed": 0, "cancelled": False}
        else:
            stats = import_new(device_id, dest_dir, items, progress, cancelled)
        stats["total"] = imported_count(device_id)
        return stats
    finally:
        if not was_mounted:
            try:
                bus.unmount(device_id)
            except BusError as exc:
                log.info("phone: unmount failed: %s", exc)


def _home_short(path: str) -> str:
    home = os.path.expanduser("~")
    return "~" + path[len(home):] if path == home or path.startswith(home + os.sep) else path


def imported_count(device_id: str) -> int:
    """Files of this phone that are imported, or were already there when it was set up."""
    return db.connect().execute("SELECT COUNT(*) FROM phone_imports WHERE device = ?",
                                (device_id,)).fetchone()[0]


class PhoneSync(QObject):
    """Phones in the Folders tab: set up, sync now, automatic sync, stop syncing."""
    availableChanged = Signal()
    devicesChanged = Signal()

    def __init__(self, gallery, settings, bus: KdeConnect | None = None, parent=None):
        super().__init__(parent)
        self.gallery = gallery
        self.settings = settings
        self.bus = bus or KdeConnect()
        self._enabled = bus is not None or supported()
        self._available = False
        self._found: list[dict] = []          # from the last look on D-Bus
        self._busy: dict[str, dict] = {}      # device id -> {done, total, mode}
        self._cancel = False
        self._forget_after: set[str] = set()  # "Stop syncing" pressed during a sync
        self._looking = False

        self._poll = QTimer(self, interval=POLL_MS)
        self._poll.timeout.connect(self.refresh)
        self._progress_timer = QTimer(self, interval=300)
        self._progress_timer.timeout.connect(self.devicesChanged.emit)
        if self._enabled:
            self._poll.start()
            QTimer.singleShot(2500, self.refresh)

    # ---- looking for phones ---------------------------------------------------------------------
    @Slot()
    def refresh(self):
        if not self._enabled or self._looking:
            return
        self._looking = True

        def done(found):
            self._looking = False
            if found is None:
                failed(None)
                return
            self._found = found
            self._set_available(True)
            for d in found:   # keep the name for when the phone is away
                entry = self.settings.phone(d["id"])
                if entry and entry.get("name") != d["name"]:
                    self.settings.set_phone(d["id"], {**entry, "name": d["name"]})
            self.devicesChanged.emit()
            self._auto_sync()

        def failed(_exc):
            self._looking = False
            self._found = []
            self._set_available(False)
            self.devicesChanged.emit()

        run_async(self.bus.phones, on_done=done, on_error=failed)

    def _set_available(self, value):
        if self._available != value:
            self._available = value
            self.availableChanged.emit()

    def _auto_sync(self):
        now = time.time()
        for d in self._found:
            entry = self.settings.phone(d["id"])
            if (entry and entry.get("auto", True) and d["reachable"] and d["browsable"]
                    and not self._busy and now - entry.get("last_try", 0) >= AUTO_SYNC_EVERY):
                self._start(d["id"], "all", quiet=True)
                return   # one phone at a time

    # ---- syncing --------------------------------------------------------------------------------
    def _device(self, device_id):
        return next((d for d in self._found if d["id"] == device_id), None)

    def _dest(self, device_id):
        entry = self.settings.phone(device_id) or {}
        name = entry.get("name") or (self._device(device_id) or {}).get("name") or device_id
        return os.path.join(phone_base_dir(), safe_folder_name(name))

    def _start(self, device_id, mode, quiet=False):
        if self._busy:
            if not quiet:
                self.gallery.toast.emit("Another phone is syncing. Try again when it's done.")
            return
        device = self._device(device_id)
        if device is None or not device["reachable"]:
            if not quiet:
                self.gallery.toast.emit("The phone isn't connected. Open KDE Connect on it and try again.")
            return
        # a phone counts as set up only once its first sync worked: if "only new ones" failed,
        # a later automatic sync must not import everything
        if self.settings.phone(device_id) is not None:
            self.settings.set_phone(device_id, {**self.settings.phone(device_id),
                                                "name": device["name"], "last_try": int(time.time())})
        state = {"done": 0, "total": 0, "mode": mode}
        self._busy[device_id] = state
        self._cancel = False
        dest = self._dest(device_id)

        def progress(done, total):
            # worker thread: only store numbers, the timer refreshes the UI
            state["done"], state["total"] = done, total

        def finished(stats):
            forgotten = device_id in self._forget_after
            self._finish(device_id)
            if forgotten:
                return
            now = int(time.time())
            entry = self.settings.phone(device_id) or {"auto": True, "since": now}
            self.settings.set_phone(device_id, {**entry, "name": device["name"], "last_try": now,
                                                "last_sync": now, "count": stats["total"]})
            if stats["imported"]:
                self._add_to_library(dest)
            if stats["imported"] or not quiet:
                self.gallery.toast.emit(self._summary(device["name"], mode, stats))

        def failed(exc):
            self._finish(device_id)
            message = str(exc) if isinstance(exc, SyncError) else f"Phone sync failed: {exc}"
            if not quiet or isinstance(exc, SyncError):
                self.gallery.toast.emit(f"{device['name']}: {message}")

        self._progress_timer.start()
        self.devicesChanged.emit()
        run_async(sync_device, self.bus, device_id, dest, mode, self.settings.phoneScreenshots,
                  progress, lambda: self._cancel, on_done=finished, on_error=failed)

    def _finish(self, device_id):
        self._busy.pop(device_id, None)
        if not self._busy:
            self._progress_timer.stop()
        if device_id in self._forget_after:
            self._forget_after.discard(device_id)
            self.forget(device_id)
        self.devicesChanged.emit()

    @staticmethod
    def _summary(name, mode, stats):
        if mode == "new":
            return f"{name} is set up. New photos will be imported from now on."
        n = stats["imported"]
        text = (f"Imported 1 new photo or video from {name}" if n == 1
                else f"Imported {n:,} new photos and videos from {name}" if n
                else f"{name}: no new photos")
        if stats["failed"]:
            text += f" ({stats['failed']} could not be copied)"
        if stats["cancelled"]:
            text += " (stopped)"
        return text

    def _add_to_library(self, dest):
        """Make sure the phone folder is in the library, then scan it."""
        for root in self.settings.folder_paths():
            if dest == root or dest.startswith(root.rstrip(os.sep) + os.sep):
                self.gallery.rescan_roots({root})
                return
        self.gallery.addFolder(phone_base_dir())

    # ---- QML ------------------------------------------------------------------------------------
    @Property(bool, notify=availableChanged)
    def available(self):
        return self._available

    @Property("QVariantList", notify=devicesChanged)
    def devices(self):
        """Phones paired with KDE Connect, set-up ones first."""
        rows, seen = [], set()
        for d in self._found:
            seen.add(d["id"])
            rows.append(self._row(d["id"], d["name"], d["reachable"], d["browsable"]))
        for device_id, entry in self.settings.phones().items():   # set up but not paired now
            if device_id not in seen:
                rows.append(self._row(device_id, entry.get("name", device_id), False, True))
        rows.sort(key=lambda r: (not r["setUp"], not r["reachable"], r["name"].lower()))
        return rows

    def _row(self, device_id, name, reachable, browsable):
        entry = self.settings.phone(device_id)
        state = self._busy.get(device_id)
        return {
            "id": device_id,
            "name": name,
            "reachable": reachable,
            "browsable": browsable,
            "setUp": entry is not None,
            "auto": bool(entry and entry.get("auto", True)),
            "lastSync": (entry or {}).get("last_sync", 0),
            "count": (entry or {}).get("count", 0),
            "busy": state is not None,
            "done": state["done"] if state else 0,
            "total": state["total"] if state else 0,
            "folder": self._dest(device_id),
            "folderLabel": _home_short(self._dest(device_id)),
        }

    @Slot(str, str)
    def setUp(self, device_id, mode):
        """First sync: mode "all" imports everything, "new" only what's taken from now on."""
        self._start(device_id, "new" if mode == "new" else "all")

    @Slot(str)
    def syncNow(self, device_id):
        self._start(device_id, "all")

    @Slot()
    def stop(self):
        self._cancel = True

    @Slot(str, bool)
    def setAuto(self, device_id, value):
        entry = self.settings.phone(device_id)
        if entry is not None:
            self.settings.set_phone(device_id, {**entry, "auto": bool(value)})
            self.devicesChanged.emit()
            if value:
                self._auto_sync()

    @Slot(str)
    def showFolder(self, device_id):
        dest = self._dest(device_id)
        if os.path.isdir(dest):
            actions.open_folder(dest)
        else:
            self.gallery.toast.emit("Nothing imported from this phone yet")

    @Slot(str)
    def forget(self, device_id):
        """Stop syncing a phone. Imported files stay where they are."""
        if device_id in self._busy:
            self._forget_after.add(device_id)
            self._cancel = True
            return
        self.settings.remove_phone(device_id)
        run_async(forget_device, device_id)
        self.devicesChanged.emit()

    def shutdown(self):
        self._cancel = True
        self._poll.stop()
