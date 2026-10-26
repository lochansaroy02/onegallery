"""The private album: password-protected, encrypted pictures and videos (see vault.py).

Moving a file in encrypts it into the album, then deletes the original and every trace of
it Gallery kept: its index entry, cached thumbnails, face crops, the editor's backup copy
and the "Open Recent" entry. Moving it out decrypts it back to its folder.

While unlocked, pictures are decrypted in memory only (image://private). Videos have to be
files for the player, so they are decrypted on demand into a private temporary folder
(in $XDG_RUNTIME_DIR, which is in RAM on most Linux systems), deleted again on lock and quit.
"""

import io
import logging
import os
import shutil
import tempfile
from pathlib import Path

from PIL import Image, ImageOps
from PySide6.QtCore import Property, QObject, QRunnable, QStandardPaths, QThreadPool, QUrl, Signal, Slot
from PySide6.QtGui import QImage
from PySide6.QtQuick import QQuickAsyncImageProvider

from . import CACHE_DIR, DATA_DIR, db, editor, thumbs, vault
from .models import PhotoModel, _day_ordinal
from .scanner import read_metadata
from .tasks import run_async
from .thumbs import _Response, _to_qimage

log = logging.getLogger(__name__)

VAULT_DIR = DATA_DIR / "private"
TEMP_PREFIX = "onegallery-private-videos-"
ID_BASE = -2_000_000_000   # private items get ids below this (library ids are positive)
RESTORE_FOLDER = "Restored from private album"


def _temp_base() -> Path:
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    return Path(runtime) if runtime and os.path.isdir(runtime) else Path(tempfile.gettempdir())


def clean_stale_temp() -> None:
    """Remove decrypted videos left behind by a crash."""
    base = _temp_base()
    uid = os.getuid() if hasattr(os, "getuid") else None
    for d in base.glob(TEMP_PREFIX + "*"):
        try:
            if d.is_dir() and (uid is None or d.stat().st_uid == uid):
                shutil.rmtree(d, ignore_errors=True)
        except OSError:
            pass


def forget_traces(path: str) -> None:
    """Remove what Gallery keeps about path: index row, faces, thumbnails, editor backup."""
    conn = db.connect()
    row = conn.execute("SELECT id FROM images WHERE path = ?", (path,)).fetchone()
    if row:
        for (face_id,) in conn.execute("SELECT id FROM faces WHERE image_id = ?", (row[0],)).fetchall():
            (CACHE_DIR / "faces" / f"{face_id}.jpg").unlink(missing_ok=True)
        with conn:
            conn.execute("DELETE FROM faces WHERE image_id = ?", (row[0],))
            conn.execute("DELETE FROM images WHERE id = ?", (row[0],))
    thumbs.forget_cached(path)
    try:
        editor.backup_path(path).unlink(missing_ok=True)
    except OSError:
        pass


def _meta_for(path: str) -> dict:
    st = os.stat(path)
    row = db.connect().execute(
        "SELECT taken, width, height, video, duration FROM images WHERE path = ?", (path,)).fetchone()
    if row:
        taken, width, height, is_video, duration = row
    else:
        meta = read_metadata(path, st.st_mtime)
        if meta is None:
            raise vault.VaultError("not a picture or video One Gallery can read")
        taken, width, height, is_video, duration = meta.taken, meta.width, meta.height, meta.video, meta.duration
    return {"name": os.path.basename(path), "path": path, "taken": int(taken), "mtime": st.st_mtime,
            "size": st.st_size, "width": width, "height": height, "video": bool(is_video),
            "duration": float(duration or 0)}


def _unique(path: Path) -> Path:
    if not path.exists():
        return path
    n = 2
    while True:
        candidate = path.with_name(f"{path.stem} ({n}){path.suffix}")
        if not candidate.exists():
            return candidate
        n += 1


class _Job(QRunnable):
    def __init__(self, provider, response, kind, item_id, width, height):
        super().__init__()
        self.provider, self.response = provider, response
        self.kind, self.item_id, self.width, self.height = kind, item_id, width, height

    def run(self):
        response, v = self.response, self.provider.vault
        try:
            if response.cancelled:
                response.finish(None, "cancelled")
                return
            if not v.unlocked:
                response.finish(None, "locked")
                return
            meta = v.item(self.item_id)
            if self.kind == "thumb" or meta.get("video"):
                image = QImage.fromData(v.read_thumbnail(self.item_id))
            else:
                w = self.width if self.width > 0 else thumbs.FULL_DEFAULT
                h = self.height if self.height > 0 else thumbs.FULL_DEFAULT
                with Image.open(io.BytesIO(v.read_bytes(self.item_id))) as im:
                    im.draft("RGB", (w, h))
                    im = ImageOps.exif_transpose(im)
                    if im.width > w or im.height > h:
                        im.thumbnail((w, h), Image.BICUBIC, reducing_gap=2.0)
                    image = _to_qimage(im)
            response.finish(image)
        except Exception as exc:
            log.debug("private image %s failed: %s", self.item_id, exc)
            response.finish(None, str(exc) or exc.__class__.__name__)
        finally:
            self.provider.live.discard(response)


class PrivateImageProvider(QQuickAsyncImageProvider):
    """image://private/thumb/<item>/<v> and image://private/full/<item>/<v>, decrypted in memory."""

    def __init__(self, vault_obj):
        super().__init__()
        self.vault = vault_obj
        self.pool = QThreadPool()
        self.pool.setMaxThreadCount(max(2, (os.cpu_count() or 4) // 2))
        self.live = set()

    def requestImageResponse(self, image_id, requested_size):
        response = _Response()
        parts = image_id.split("/")
        if len(parts) < 2 or parts[0] not in ("thumb", "full") or not parts[1].isalnum():
            response.finish(None, "bad id")
            return response
        self.live.add(response)
        self.pool.start(_Job(self, response, parts[0], parts[1],
                             requested_size.width(), requested_size.height()))
        return response


class PrivateAlbum(QObject):
    stateChanged = Signal()
    busyChanged = Signal()
    unlockFinished = Signal(bool, str)        # ok, message
    createFinished = Signal(bool, str)
    passwordChanged = Signal(bool, str)
    videoPrepared = Signal(str)               # item id

    def __init__(self, gallery, settings, parent=None):
        super().__init__(parent)
        self.gallery, self.settings = gallery, settings
        self.vault = vault.Vault(VAULT_DIR)
        self.photos = PhotoModel(settings.columns, "none", auto_load=False, parent=self)
        self.photos.items_source = self._items
        self.photos.url_source = self._video_url
        settings.columnsChanged.connect(lambda: setattr(self.photos, "columns", settings.columns))
        settings.sortAscendingChanged.connect(lambda: self.photos.reload() if self.vault.unlocked else None)
        self._ids: dict[str, int] = {}
        self._uids: dict[int, str] = {}
        self._busy = 0
        self._videos: dict[str, str] = {}
        self._video_jobs: set[str] = set()
        self._temp: Path | None = None
        clean_stale_temp()
        if vault.AVAILABLE:
            gallery.albums.extra_albums = self._album_entry
            self.stateChanged.connect(gallery.albums.reload)
            gallery.albums.reload()

    def _album_entry(self) -> list[dict]:
        return [{"key": "", "kind": "private", "title": self.tr("Private album"), "subtitle": "",
                 "count": self.count, "cover": "", "available": True, "latest": 0}]

    # ---- state -------------------------------------------------------------------------------
    @Property(bool, constant=True)
    def supported(self):
        return vault.AVAILABLE

    @Property(bool, notify=stateChanged)
    def exists(self):
        return self.vault.exists

    @Property(bool, notify=stateChanged)
    def unlocked(self):
        return self.vault.unlocked

    @Property(bool, notify=busyChanged)
    def busy(self):
        return self._busy > 0

    def _set_busy(self, delta):
        self._busy = max(0, self._busy + delta)
        self.busyChanged.emit()

    def _run(self, fn, *args, on_done=None, on_error=None):
        self._set_busy(1)

        def done(result):
            self._set_busy(-1)
            if on_done:
                on_done(result)

        def failed(exc):
            self._set_busy(-1)
            log.warning("private album: %s", exc)
            if on_error:
                on_error(exc)
            else:
                self.gallery.toast.emit(str(exc) or "Private album error")

        run_async(fn, *args, on_done=done, on_error=failed)

    # ---- password ----------------------------------------------------------------------------
    @Slot(str)
    def create(self, password):
        def done(_):
            self.stateChanged.emit()
            self.photos.setFilter("private", "")
            self.createFinished.emit(True, "")

        self._run(self.vault.create, password, on_done=done,
                  on_error=lambda exc: self.createFinished.emit(False, str(exc)))

    @Slot(str)
    def unlock(self, password):
        def done(_):
            self.stateChanged.emit()
            self.photos.setFilter("private", "")
            self.photos.reload()
            self.unlockFinished.emit(True, "")

        self._run(self.vault.unlock, password, on_done=done,
                  on_error=lambda exc: self.unlockFinished.emit(False, str(exc)))

    @Slot()
    def lock(self):
        if self._temp is not None:
            shutil.rmtree(self._temp, ignore_errors=True)
            self._temp = None
        self._videos.clear()
        was = self.vault.unlocked
        self.vault.lock()
        self.photos.setFilter("none", "")
        if was:
            self.stateChanged.emit()

    @Slot(str, str)
    def changePassword(self, old, new):
        self._run(self.vault.change_password, old, new,
                  on_done=lambda _: self.passwordChanged.emit(True, "Password changed"),
                  on_error=lambda exc: self.passwordChanged.emit(False, str(exc)))

    @Slot()
    def destroy(self):
        """Delete the private album and everything in it (for a forgotten password)."""
        self.lock()
        self.vault.destroy()
        self.stateChanged.emit()
        self.gallery.toast.emit("Private album deleted")

    # ---- items -------------------------------------------------------------------------------------
    def _id_for(self, uid: str) -> int:
        iid = self._ids.get(uid)
        if iid is None:
            iid = ID_BASE - len(self._ids) - 1
            self._ids[uid], self._uids[iid] = iid, uid
        return iid

    def _items(self) -> list[list]:
        if not self.vault.unlocked:
            return []
        rows = []
        for m in self.vault.items():
            taken = int(m.get("taken") or m.get("mtime") or 0)
            rows.append([self._id_for(m["id"]), f"{m['id']}/{m.get('name', '')}", taken, m.get("added", 0),
                         m.get("width", 0), m.get("height", 0), m.get("size", 0), 1, 0,
                         int(bool(m.get("video"))), float(m.get("duration") or 0), _day_ordinal(taken)])
        ascending = self.settings.sortAscending
        rows.sort(key=lambda r: (r[2], r[1]), reverse=not ascending)
        return rows

    def uids(self, ids) -> list[str]:
        return [self._uids[int(i)] for i in ids if int(i) in self._uids]

    @Property(int, notify=stateChanged)
    def count(self):
        return len(self.vault.items()) if self.vault.unlocked else 0

    # ---- videos ------------------------------------------------------------------------------------
    def _video_url(self, uid: str) -> str:
        if uid in self._videos:
            return self._videos[uid]
        if uid not in self._video_jobs and self.vault.unlocked:
            self._video_jobs.add(uid)
            if self._temp is None:
                self._temp = Path(tempfile.mkdtemp(prefix=TEMP_PREFIX, dir=_temp_base()))
                os.chmod(self._temp, 0o700)
            meta = self.vault.item(uid)
            dest = self._temp / f"{uid}{os.path.splitext(meta.get('name', ''))[1] or '.mp4'}"

            def done(_):
                self._video_jobs.discard(uid)
                if self.vault.unlocked and self._temp is not None:
                    self._videos[uid] = QUrl.fromLocalFile(str(dest)).toString()
                    self.videoPrepared.emit(uid)

            def failed(exc):
                self._video_jobs.discard(uid)
                self.gallery.toast.emit(f"Couldn't open the video: {exc}")

            run_async(self.vault.decrypt_to, uid, dest, on_done=done, on_error=failed)
        return ""

    # ---- move in / out, delete ----------------------------------------------------------------------
    @Slot("QStringList", bool)
    def moveIn(self, paths, relock=False):
        """Encrypt paths into the album. relock: lock it again afterwards (it was unlocked
        only to move these in)."""
        paths = [p for p in paths if p and not p.startswith("private:")]
        if not paths:
            return
        if not self.vault.unlocked:
            self.gallery.toast.emit("Unlock the private album first")
            return

        def work():
            moved, failed = [], []
            for path in paths:
                uid = None
                try:
                    meta = _meta_for(path)
                    uid = self.vault.add(path, meta, thumbs.thumbnail_jpeg(path))
                    os.remove(path)            # the encrypted copy is safe: drop the original
                except Exception as exc:
                    if uid:                    # couldn't delete the original: don't keep a copy
                        self.vault.remove(uid)
                    log.warning("could not move %s to the private album: %s", path, exc)
                    failed.append((path, str(exc)))
                    continue
                forget_traces(path)
                moved.append(path)
            return moved, failed

        def done(result):
            moved, failed = result
            self.settings.remove_recent(moved)
            self.gallery.reloadLibrary()
            self.photos.reload()
            self.stateChanged.emit()
            if moved:
                self.gallery.toast.emit(
                    f"Moved {len(moved)} {'item' if len(moved) == 1 else 'items'} to the private album"
                    + (f" ({len(failed)} failed)" if failed else ""))
            elif failed:
                self.gallery.toast.emit(f"Couldn't move to the private album: {failed[0][1]}")
            if relock:
                self.lock()

        self.gallery.toast.emit("Moving to the private album…")
        self._run(work, on_done=done)

    @Slot("QVariantList")
    def moveOut(self, ids):
        uids = self.uids(ids)
        if not uids:
            return

        def work():
            restored = []
            pictures = QStandardPaths.writableLocation(QStandardPaths.PicturesLocation) or os.path.expanduser("~")
            for uid in uids:
                meta = self.vault.item(uid)
                original = Path(meta.get("path") or "")
                folder = original.parent
                if not original.name or not folder.is_dir() or not os.access(folder, os.W_OK):
                    folder = Path(pictures) / RESTORE_FOLDER
                    folder.mkdir(parents=True, exist_ok=True)
                dest = _unique(folder / (meta.get("name") or original.name or f"{uid}.jpg"))
                self.vault.decrypt_to(uid, dest)
                if meta.get("mtime"):
                    os.utime(dest, (meta["mtime"], meta["mtime"]))
                self.vault.remove(uid)
                restored.append(str(dest))
            return restored

        def done(restored):
            roots = {r for r in self.settings.folder_paths()
                     for p in restored if p.startswith(r.rstrip(os.sep) + os.sep)}
            if roots:
                self.gallery.rescan_roots(roots)
            self.photos.reload()
            self.stateChanged.emit()
            where = os.path.dirname(restored[0]) if restored else ""
            self.gallery.toast.emit(f"Moved {len(restored)} out of the private album"
                                    + (f" to {os.path.basename(where)}" if where else ""))

        self._run(work, on_done=done)

    @Slot("QVariantList")
    def deleteItems(self, ids):
        uids = self.uids(ids)

        def work():
            for uid in uids:
                self.vault.remove(uid)
            return len(uids)

        def done(n):
            self.photos.reload()
            self.stateChanged.emit()
            self.gallery.toast.emit(f"Deleted {n} {'item' if n == 1 else 'items'} permanently")

        self._run(work, on_done=done)

    def shutdown(self):
        self.lock()
