"""Backend smoke tests.  Run:  python -m unittest discover -s tests -v"""

import os
import shutil
import sys
import tempfile
import time
import unittest

TMP = tempfile.mkdtemp(prefix="onegallery-test-")
os.environ["ONEGALLERY_HOME"] = os.path.join(TMP, "home")
os.environ["XDG_DATA_HOME"] = os.path.join(TMP, "xdg-data")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

from PIL import Image  # noqa: E402
from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402

import make_samples  # noqa: E402
from backend import actions, db, scanner, thumbs  # noqa: E402
from backend.models import AlbumModel, PhotoModel, build_filter  # noqa: E402
from backend.settings import Settings  # noqa: E402

app = QGuiApplication.instance() or QGuiApplication(sys.argv)
SAMPLES = os.path.join(TMP, "samples")
N = 150


def wait_for(predicate, timeout=10.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        QCoreApplication.processEvents(QEventLoop.AllEvents, 50)
        if predicate():
            return True
        time.sleep(0.01)
    return False


def setUpModule():
    db.init()
    for i in range(N):
        make_samples.make_one((SAMPLES, i, 1000 + i, 2))
    make_samples.make_broken(SAMPLES)


def tearDownModule():
    shutil.rmtree(TMP, ignore_errors=True)


def entry(path=SAMPLES, mount="/"):
    return {"path": path, "mount": mount}


class ScannerTests(unittest.TestCase):
    def test_1_full_scan_skips_junk(self):
        with db.connect() as conn:
            conn.execute("DELETE FROM images")
        stats = scanner.scan_root(entry())
        self.assertEqual(stats["found"] - stats["errors"], N)
        self.assertEqual(stats["added"], N)
        self.assertGreaterEqual(stats["errors"], 2)  # corrupt.jpg + not_an_image.png
        names = {r[0] for r in db.connect().execute("SELECT name FROM images")}
        self.assertNotIn("secret.bmp", names)       # hidden folder
        self.assertNotIn("tiny_icon.png", names)    # below min size
        self.assertNotIn("corrupt.jpg", names)

    def test_2_incremental(self):
        stats = scanner.scan_root(entry())
        self.assertEqual((stats["added"], stats["updated"], stats["removed"]), (0, 0, 0))
        conn = db.connect()
        path = conn.execute("SELECT path FROM images WHERE name LIKE 'IMG_%' LIMIT 1").fetchone()[0]
        os.utime(path, (time.time(), time.time()))
        victim = conn.execute(
            "SELECT path FROM images WHERE path != ? LIMIT 1", (path,)).fetchone()[0]
        os.unlink(victim)
        stats = scanner.scan_root(entry())
        self.assertEqual((stats["added"], stats["updated"], stats["removed"]), (0, 1, 1))

    def test_3_exif_date_used(self):
        rows = db.connect().execute("SELECT name, taken FROM images WHERE name LIKE 'IMG_%'")
        matched = 0
        for name, taken in rows:
            stamp = name.split("_")[1] + name.split("_")[2]
            if time.strftime("%Y%m%d%H%M%S", time.localtime(taken)) == stamp:
                matched += 1
        self.assertGreater(matched, 0)

    def test_4_unmounted_drive_keeps_entries(self):
        before = db.connect().execute("SELECT COUNT(*) FROM images").fetchone()[0]
        stats = scanner.scan_root(entry(mount="/definitely/not/mounted"))
        self.assertTrue(stats.get("unavailable"))
        conn = db.connect()
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM images").fetchone()[0], before)
        self.assertEqual(conn.execute("SELECT SUM(available) FROM images").fetchone()[0], 0)
        scanner.scan_root(entry())  # drive "comes back"
        self.assertEqual(conn.execute("SELECT SUM(available) FROM images").fetchone()[0], before)

    def test_5_exif_parsing(self):
        self.assertIsNone(scanner.parse_exif_date("0000:00:00 00:00:00"))
        self.assertIsNotNone(scanner.parse_exif_date("2024:10:05 12:00:00\x00"))
        self.assertIsNotNone(scanner.parse_exif_date(b"2024:10:05 12:00:00"))


class ModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        scanner.scan_root(entry())

    def test_grid_rows_and_sections(self):
        model = PhotoModel(columns=4)
        self.assertTrue(wait_for(lambda: model.itemCount > 0))
        total = sum(len(model.data(model.index(r), PhotoModel.ItemsRole))
                    for r in range(model.rowCount()))
        self.assertEqual(total, model.itemCount)
        for r in range(model.rowCount()):
            self.assertLessEqual(len(model.data(model.index(r), PhotoModel.ItemsRole)), 4)
        day = model.data(model.index(0), PhotoModel.SectionRole)
        self.assertTrue(model.dayLabel(day))
        model.toggleDay(day)
        self.assertTrue(model.isDaySelected(day))
        self.assertGreater(model.selectionCount, 0)
        model.columns = 7
        self.assertEqual(model.rowForItem(0), 0)
        model.clearSelection()
        self.assertEqual(model.selectionCount, 0)

    def test_search_filter(self):
        where, params = build_filter("search", "2025 October lisbon")
        self.assertEqual(params[:2], ["2025", "10"])
        model = PhotoModel(columns=4, kind="search", value="Screenshot")
        self.assertTrue(wait_for(lambda: not model.loading))
        self.assertGreater(model.itemCount, 0)
        self.assertTrue(all("Screenshot" in model.itemAt(i)["name"] for i in range(model.itemCount)))

    def test_albums(self):
        settings = Settings()
        settings.albumsBySubfolder = True
        albums = AlbumModel(settings)
        self.assertTrue(wait_for(lambda: albums.count > 1))


class SettingsTests(unittest.TestCase):
    def test_add_remove_nested(self):
        s = Settings()
        sub = os.path.join(SAMPLES, "Camera")
        self.assertEqual(s.add_folder(sub)[0], "")
        err, replaced = s.add_folder(SAMPLES)
        self.assertEqual(err, "")
        self.assertEqual(replaced, [sub])
        self.assertIn("Already", s.add_folder(sub)[0])
        self.assertTrue(s.remove_folder(SAMPLES))
        self.assertEqual(s.folder_paths(), [])


class ThumbAndTrashTests(unittest.TestCase):
    def test_thumbnail_orientation(self):
        src = os.path.join(TMP, "rotated.jpg")
        exif = Image.Exif()
        exif[274] = 6  # rotate 90 CW on display
        Image.new("RGB", (800, 400), "green").save(src, exif=exif)
        out = thumbs.cache_path(src, 1)
        im = thumbs.make_thumbnail(src, out)
        self.assertTrue(out.exists())
        self.assertLess(im.width, im.height)  # portrait after transpose
        self.assertEqual(min(im.size), thumbs.THUMB_SHORT_SIDE)

    @unittest.skipIf(sys.platform == "win32", "the freedesktop trash is Linux-only (Windows: Recycle Bin)")
    def test_freedesktop_trash(self):
        victim = os.path.join(os.environ["XDG_DATA_HOME"], "victim.jpg")
        os.makedirs(os.path.dirname(victim), exist_ok=True)
        Image.new("RGB", (10, 10)).save(victim)
        actions.freedesktop_trash(victim)
        trash = os.path.join(os.environ["XDG_DATA_HOME"], "Trash")
        self.assertFalse(os.path.exists(victim))
        self.assertTrue(os.path.exists(os.path.join(trash, "files", "victim.jpg")))
        with open(os.path.join(trash, "info", "victim.jpg.trashinfo")) as f:
            info = f.read()
        self.assertIn("Path=", info)


if __name__ == "__main__":
    unittest.main()
