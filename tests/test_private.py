"""Private album: encryption, password, move in / out.  Run: python -m unittest discover -s tests"""

import os
import shutil
import sys
import tempfile
import time
import unittest

TMP = tempfile.mkdtemp(prefix="onegallery-private-test-")
os.environ.setdefault("ONEGALLERY_HOME", os.path.join(TMP, "home"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from PIL import Image  # noqa: E402
from PySide6.QtCore import QCoreApplication, QEventLoop  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402

from backend import db, scanner, thumbs, vault  # noqa: E402

app = QGuiApplication.instance() or QGuiApplication([])


def tearDownModule():
    shutil.rmtree(TMP, ignore_errors=True)


def wait_for(pred, timeout=20):
    end = time.time() + timeout
    while time.time() < end:
        QCoreApplication.processEvents(QEventLoop.AllEvents, 50)
        if pred():
            return True
        time.sleep(0.01)
    return False


@unittest.skipUnless(vault.AVAILABLE, "python-cryptography not installed")
class VaultTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(dir=TMP)
        self.v = vault.Vault(os.path.join(self.dir, "v"))
        self.v.create("correct horse")

    def blob(self, size):
        path = os.path.join(self.dir, f"f{size}.bin")
        with open(path, "wb") as f:
            f.write(os.urandom(size))
        return path

    def test_roundtrip_sizes(self):
        for size in (0, 1, vault.CHUNK - 1, vault.CHUNK, vault.CHUNK + 1, 2 * vault.CHUNK + 5):
            src = self.blob(size)
            uid = self.v.add(src, {"name": "x"}, b"thumb")
            with open(src, "rb") as f:
                self.assertEqual(self.v.read_bytes(uid), f.read(), size)
            self.assertEqual(self.v.read_thumbnail(uid), b"thumb")

    def test_ciphertext_hides_content(self):
        src = os.path.join(self.dir, "plain.txt")
        with open(src, "wb") as f:
            f.write(b"SECRET-PICTURE-CONTENT" * 1000)
        uid = self.v.add(src, {"name": "plain.txt", "path": src}, b"t")
        for name in os.listdir(self.v.items_dir) + ["../manifest.bin"]:
            with open(os.path.join(self.v.items_dir, name), "rb") as f:
                data = f.read()
            self.assertNotIn(b"SECRET-PICTURE", data)
            self.assertNotIn(b"plain.txt", data)    # names are encrypted too
        self.assertTrue(self.v.read_bytes(uid).startswith(b"SECRET"))

    def test_password(self):
        self.v.add(self.blob(10), {"name": "a"}, b"t")
        self.v.lock()
        self.assertFalse(self.v.unlocked)
        with self.assertRaises(vault.VaultError):
            self.v.items()
        with self.assertRaises(vault.WrongPassword):
            self.v.unlock("wrong")
        self.v.unlock("correct horse")
        self.assertEqual(len(self.v.items()), 1)
        self.v.change_password("correct horse", "new pass")
        self.v.lock()
        with self.assertRaises(vault.WrongPassword):
            self.v.unlock("correct horse")
        self.v.unlock("new pass")
        self.assertEqual(len(self.v.items()), 1)   # same key, same items

    def test_tampering_is_detected(self):
        uid = self.v.add(self.blob(vault.CHUNK + 100), {"name": "a"}, b"t")
        path = self.v.items_dir / f"{uid}.bin"
        data = bytearray(path.read_bytes())
        data[100] ^= 1
        path.write_bytes(bytes(data))
        with self.assertRaises(vault.VaultError):
            self.v.read_bytes(uid)
        good = self.v.add(self.blob(vault.CHUNK + 100), {"name": "b"}, b"t")
        p2 = self.v.items_dir / f"{good}.bin"
        p2.write_bytes(p2.read_bytes()[:-50])          # cut off
        with self.assertRaises(vault.VaultError):
            self.v.read_bytes(good)

    def test_destroy(self):
        self.v.destroy()
        self.assertFalse(self.v.exists)
        self.assertFalse(os.path.exists(self.v.root))


@unittest.skipUnless(vault.AVAILABLE, "python-cryptography not installed")
class AlbumTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from backend.controller import Gallery
        from backend.private import PrivateAlbum
        from backend.settings import Settings

        db.init()
        cls.root = os.path.join(TMP, "Pictures")
        os.makedirs(cls.root)
        cls.files = []
        for i in range(3):
            p = os.path.join(cls.root, f"p{i}.jpg")
            exif = Image.Exif()
            exif.get_ifd(0x8769)[36867] = f"2024:05:0{i + 1} 10:00:00"
            Image.effect_noise((300, 200), 40).convert("RGB").save(p, exif=exif)
            cls.files.append(p)
        cls.settings = Settings()
        cls.settings.add_folder(cls.root)
        scanner.scan_root({"path": cls.root, "mount": "/"}, min_size_kb=0)
        cls.gallery = Gallery(cls.settings)
        cls.album = PrivateAlbum(cls.gallery, cls.settings)
        cls.messages = []
        cls.gallery.toast.connect(cls.messages.append)

    def rows(self):
        return db.connect().execute("SELECT COUNT(*) FROM images WHERE root = ?", (self.root,)).fetchone()[0]

    def test_flow(self):
        a = self.album
        results = []
        a.createFinished.connect(lambda ok, msg: results.append(ok))
        a.create("pw123456")
        self.assertTrue(wait_for(lambda: results == [True]))
        self.assertTrue(a.unlocked)

        # thumbnail cached for the picture before it moves in: must be removed too
        cached = thumbs.cache_path(self.files[0], "1-1")
        thumbs.make_thumbnail(self.files[0], cached)
        self.assertTrue(cached.exists())

        a.moveIn(self.files[:2])
        self.assertTrue(wait_for(lambda: not a.busy and a.photos.itemCount == 2))
        self.assertFalse(os.path.exists(self.files[0]))           # original gone
        self.assertFalse(cached.exists())                         # its thumbnail too
        self.assertEqual(self.rows(), 1)                          # out of the index
        info = a.photos.itemAt(0)
        self.assertTrue(info["private"])
        self.assertTrue(info["thumb"].startswith("image://private/thumb/"))
        self.assertIn(info["name"], ("p0.jpg", "p1.jpg"))

        a.lock()
        self.assertEqual(a.photos.itemCount, 0)
        unlocked = []
        a.unlockFinished.connect(lambda ok, msg: unlocked.append((ok, msg)))
        a.unlock("nope")
        self.assertTrue(wait_for(lambda: len(unlocked) == 1))
        self.assertEqual(unlocked[0][0], False)
        a.unlock("pw123456")
        self.assertTrue(wait_for(lambda: len(unlocked) == 2 and a.photos.itemCount == 2))

        ids = [a.photos.idAt(i) for i in range(2)]
        a.moveOut(ids[:1])
        self.assertTrue(wait_for(lambda: not a.busy and a.photos.itemCount == 1))
        restored = [f for f in self.files[:2] if os.path.exists(f)]
        self.assertEqual(len(restored), 1)                         # back where it was
        self.assertTrue(wait_for(lambda: self.rows() == 2, 15))    # and back in the library

        a.deleteItems([a.photos.idAt(0)])
        self.assertTrue(wait_for(lambda: not a.busy and a.photos.itemCount == 0))
        self.assertEqual(len(a.vault.items()), 0)
        a.destroy()
        self.assertFalse(a.exists)


if __name__ == "__main__":
    unittest.main()
