"""Opening pictures from a file manager + default image viewer.  Run: python -m unittest discover -s tests"""

import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

TMP = tempfile.mkdtemp(prefix="onegallery-ext-test-")
os.environ.setdefault("ONEGALLERY_HOME", os.path.join(TMP, "home"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from PIL import Image  # noqa: E402

from backend import actions, db, external, scanner  # noqa: E402


def tearDownModule():
    shutil.rmtree(TMP, ignore_errors=True)


class ExternalFolderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.init()
        cls.folder = os.path.join(TMP, "Downloads")
        os.makedirs(cls.folder)
        for name in ("IMG_10.jpg", "img_2.png", "IMG_1.jpg", ".hidden.jpg", "notes.txt", "broken.jpg"):
            path = os.path.join(cls.folder, name)
            if name.endswith(".txt") or name == "broken.jpg":
                with open(path, "w") as f:
                    f.write("not an image")
            else:
                Image.new("RGB", (64, 48), "red").save(path)

    def test_natural_order_and_filtering(self):
        names = [os.path.basename(p) for p in external.list_folder(self.folder)]
        self.assertEqual(names, ["broken.jpg", "IMG_1.jpg", "img_2.png", "IMG_10.jpg"])

    def test_items_are_not_indexed(self):
        before = db.connect().execute("SELECT COUNT(*) FROM images").fetchone()[0]
        items = external.load_items(external.list_folder(self.folder))
        names = [os.path.basename(i[1]) for i in items]
        self.assertEqual(names, ["IMG_1.jpg", "img_2.png", "IMG_10.jpg"])  # broken file skipped
        self.assertTrue(all(i[0] < 0 for i in items))
        self.assertEqual(external.lookup(items[0][0]), items[0][1])
        self.assertEqual(items[0][4:6], [64, 48])
        after = db.connect().execute("SELECT COUNT(*) FROM images").fetchone()[0]
        self.assertEqual(before, after)

    def test_library_files_keep_their_real_id(self):
        lib = os.path.join(TMP, "lib")
        os.makedirs(lib)
        path = os.path.join(lib, "a.jpg")
        Image.effect_noise((300, 300), 50).convert("RGB").save(path)
        scanner.scan_root({"path": lib, "mount": "/"}, min_size_kb=0)
        real_id = db.connect().execute("SELECT id FROM images WHERE path = ?", (path,)).fetchone()[0]
        items = external.load_items([path])
        self.assertEqual(items[0][0], real_id)

    def test_paths_from_args(self):
        jpg = os.path.join(self.folder, "IMG_1.jpg")
        args = ["--new-instance", "file://" + jpg, jpg, os.path.join(self.folder, "notes.txt"),
                os.path.join(self.folder, "missing.jpg")]
        self.assertEqual(external.paths_from_args(args), [jpg])


class DefaultViewerTests(unittest.TestCase):
    """The freedesktop way (mimeapps.list), also when the tests run on a Mac."""

    def setUp(self):
        patch = mock.patch.object(actions, "IS_MAC", False)
        patch.start()
        self.addCleanup(patch.stop)
        self.env = {k: os.environ.get(k) for k in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "PATH")}
        self.config = os.path.join(TMP, "cfg")
        self.data = os.path.join(TMP, "data")
        os.makedirs(os.path.join(self.data, "applications"), exist_ok=True)
        os.environ["XDG_CONFIG_HOME"] = self.config
        os.environ["XDG_DATA_HOME"] = self.data
        os.environ["PATH"] = "/nonexistent"  # force the built-in mimeapps.list writer
        os.makedirs(self.config, exist_ok=True)
        with open(os.path.join(self.config, "mimeapps.list"), "w") as f:
            f.write("[Default Applications]\nimage/png=org.kde.gwenview.desktop;\ntext/plain=kate.desktop;\n")

    def tearDown(self):
        for k, v in self.env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_not_installed(self):
        self.assertEqual(actions.default_viewer_status(["image/png"]), "not-installed")
        with self.assertRaises(RuntimeError):
            actions.set_default_viewer(["image/png"])

    def test_set_default(self):
        with open(os.path.join(self.data, "applications", "onegallery.desktop"), "w") as f:
            f.write("[Desktop Entry]\nType=Application\nName=Gallery\nExec=onegallery %F\n")
        mimes = ["image/jpeg", "image/png"]
        self.assertEqual(actions.default_viewer_status(mimes), "other")
        actions.set_default_viewer(mimes)
        self.assertEqual(actions.default_viewer_status(mimes), "default")
        with open(os.path.join(self.config, "mimeapps.list")) as f:
            text = f.read()
        self.assertIn("text/plain=kate.desktop;", text)      # other associations untouched
        self.assertIn("image/png=onegallery.desktop;", text)


if __name__ == "__main__":
    unittest.main()
