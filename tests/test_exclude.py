"""Excluded sub-folders.  Run: python -m unittest discover -s tests"""

import os
import shutil
import sys
import tempfile
import unittest

TMP = tempfile.mkdtemp(prefix="onegallery-exclude-test-")
os.environ.setdefault("ONEGALLERY_HOME", os.path.join(TMP, "home"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from PIL import Image  # noqa: E402

from backend import db, scanner  # noqa: E402
from backend.settings import Settings  # noqa: E402
from backend.watcher import _Handler  # noqa: E402


def tearDownModule():
    shutil.rmtree(TMP, ignore_errors=True)


def make(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    Image.effect_noise((200, 200), 40).convert("RGB").save(path)


class ExcludeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.init()
        cls.root = os.path.join(TMP, "Pictures")
        for rel in ("a.jpg", "Trips/t1.jpg", "Trips/Alps/x1.jpg", "Trips/Alps/Deep/x2.jpg",
                    "Screenshots/s1.png", "Screenshots/s2.png"):
            make(os.path.join(cls.root, rel))

    def count(self):
        return db.connect().execute(
            "SELECT COUNT(*) FROM images WHERE root = ?", (self.root,)).fetchone()[0]

    def test_scan_settings_and_watch(self):
        s = Settings()
        self.assertEqual(s.add_folder(self.root)[0], "")
        entry = lambda: next(e for e in s.folder_entries() if e["path"] == self.root)  # noqa: E731
        scanner.scan_root(entry(), min_size_kb=0)
        self.assertEqual(self.count(), 6)

        alps = os.path.join(self.root, "Trips", "Alps")
        shots = os.path.join(self.root, "Screenshots")
        # nested entries collapse, paths outside the folder are ignored
        self.assertTrue(s.set_excludes(self.root, [alps, os.path.join(alps, "Deep"), shots, "/etc"]))
        self.assertEqual(s.excludes(self.root), [shots, alps])
        stats = scanner.scan_root(entry(), min_size_kb=0)
        self.assertEqual(stats["removed"], 4)
        self.assertEqual(self.count(), 2)
        self.assertTrue(os.path.exists(os.path.join(alps, "x1.jpg")))  # files untouched

        # live updates ignore excluded folders
        events = []
        handler = _Handler(self.root, events.append, s.excludes(self.root))
        self.assertFalse(handler._relevant(os.path.join(alps, "new.jpg")))
        self.assertFalse(handler._relevant(os.path.join(alps, "Deep", "new.jpg")))
        self.assertTrue(handler._relevant(os.path.join(self.root, "Trips", "new.jpg")))

        # a folder inside an excluded area may be watched on its own
        self.assertEqual(s.add_folder(alps)[0], "")
        self.assertIn("Already included", s.add_folder(os.path.join(self.root, "Trips"))[0])
        s.remove_folder(alps)

        # including again brings the pictures back
        self.assertTrue(s.set_excludes(self.root, [shots]))
        scanner.scan_root(entry(), min_size_kb=0)
        self.assertEqual(self.count(), 4)
        self.assertFalse(s.set_excludes(self.root, [shots]))  # unchanged


if __name__ == "__main__":
    unittest.main()
