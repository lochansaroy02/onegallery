"""Editor pipeline and save / save-as-copy / revert tests.  Run: python -m unittest discover -s tests"""

import os
import shutil
import sys
import tempfile
import time
import unittest

TMP = tempfile.mkdtemp(prefix="onegallery-edit-test-")
os.environ.setdefault("ONEGALLERY_HOME", os.path.join(TMP, "home"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from PIL import Image  # noqa: E402

from backend import db, editor, scanner  # noqa: E402
from backend.editor import DEFAULTS, apply_geometry, render  # noqa: E402


def params(**changes):
    p = {k: (list(v) if isinstance(v, list) else v) for k, v in DEFAULTS.items()}
    p.update(changes)
    return p


def make_photo(path, size=(400, 200), exif_date="2021:06:15 10:30:00", mtime=None):
    im = Image.new("RGB", size, (200, 40, 40))
    im.paste((40, 200, 40), (0, 0, size[0] // 2, size[1] // 2))   # green top-left
    exif = Image.Exif()
    if exif_date:
        exif.get_ifd(0x8769)[36867] = exif_date
    im.save(path, quality=95, exif=exif)
    if mtime:
        os.utime(path, (mtime, mtime))
    return path


def tearDownModule():
    shutil.rmtree(TMP, ignore_errors=True)


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.im = Image.open(make_photo(os.path.join(TMP, "p.jpg"))).convert("RGB")

    def test_defaults_are_identity(self):
        out = render(self.im, params())
        self.assertEqual(out.size, self.im.size)
        self.assertEqual(out.tobytes(), self.im.tobytes())

    def test_rotate_flip(self):
        out = apply_geometry(self.im, params(rotate=90))
        self.assertEqual(out.size, (200, 400))
        # rotating left moves the green top-left corner to the bottom-left
        self.assertGreater(out.getpixel((5, 395))[1], 150)
        flipped = apply_geometry(self.im, params(flipH=True))
        self.assertGreater(flipped.getpixel((395, 5))[1], 150)

    def test_crop_and_straighten_keep_sizes(self):
        out = apply_geometry(self.im, params(crop=[0.25, 0.25, 0.5, 0.5]))
        self.assertEqual(out.size, (200, 100))
        out = apply_geometry(self.im, params(straighten=10.0))
        self.assertEqual(out.size, self.im.size)

    def test_adjustments_and_filters(self):
        darker = render(self.im, params(exposure=-0.8))
        self.assertLess(sum(darker.getpixel((300, 150))), sum(self.im.getpixel((300, 150))))
        mono = render(self.im, params(filter="mono"))
        r, g, b = mono.getpixel((300, 150))
        self.assertLessEqual(max(r, g, b) - min(r, g, b), 2)

    def test_rotate_left_keeps_visual_crop(self):
        ed = editor.Editor()
        ed._base = self.im
        ed._params = params(crop=[0.0, 0.0, 0.5, 0.5])  # top-left quarter
        ed.rotateLeft()
        rotated_crop = apply_geometry(self.im, ed._params)
        # the cropped region is still the green quarter
        self.assertGreater(rotated_crop.getpixel((10, 10))[1], 150)


class SaveRevertTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.init()
        cls.folder = os.path.join(TMP, "lib")
        os.makedirs(cls.folder, exist_ok=True)
        cls.with_exif = make_photo(os.path.join(cls.folder, "a.jpg"))
        cls.no_exif = make_photo(os.path.join(cls.folder, "b.jpg"), exif_date=None,
                                 mtime=time.mktime((2019, 3, 4, 12, 0, 0, 0, 0, -1)))
        scanner.scan_root({"path": cls.folder, "mount": "/"}, min_size_kb=0)

    def row(self, path):
        r = db.connect().execute(
            "SELECT root, dir, taken, mtime, width, height FROM images WHERE path = ?", (path,)).fetchone()
        return dict(zip(("root", "dir", "taken", "mtime", "width", "height"), r)) if r else None

    def test_save_backup_and_revert(self):
        path = self.with_exif
        with open(path, "rb") as f:
            original = f.read()
        before = self.row(path)
        editor.save_job(path, path, params(rotate=90), before, overwrite=True)
        self.assertTrue(editor.has_original(path))
        after = self.row(path)
        self.assertEqual((after["width"], after["height"]), (200, 400))
        self.assertEqual(after["taken"], before["taken"])          # still sorted on the same day
        with Image.open(path) as im:
            self.assertEqual(im.getexif().get(274), 1)
            self.assertEqual(im.getexif().get_ifd(0x8769).get(36867), "2021:06:15 10:30:00")
        # a second save must keep the very first original
        editor.save_job(path, path, params(flipH=True), after, overwrite=True)
        editor.revert_job(path)
        with open(path, "rb") as f:
            self.assertEqual(f.read(), original)
        self.assertFalse(editor.has_original(path))
        self.assertEqual((self.row(path)["width"], self.row(path)["height"]), (400, 200))

    def test_save_copy_inherits_date(self):
        path = self.no_exif
        row = self.row(path)
        dest = editor.copy_name(path)
        self.assertTrue(dest.endswith("b_edited.jpg"))
        editor.save_job(path, dest, params(filter="mono"), row, overwrite=False)
        self.assertTrue(editor.copy_name(path).endswith(os.sep + "b_edited_2.jpg"))
        copy_row = self.row(dest)
        self.assertIsNotNone(copy_row)
        self.assertEqual(copy_row["taken"], row["taken"])
        # the date was embedded so a rescan keeps it as well
        with Image.open(dest) as im:
            self.assertTrue(im.getexif().get_ifd(0x8769).get(36867).startswith("2019:03:04"))
        self.assertFalse(editor.has_original(path))                 # original untouched
        stats = scanner.scan_root({"path": self.folder, "mount": "/"}, min_size_kb=0)
        self.assertEqual(stats["added"], 0)
        self.assertEqual(self.row(dest)["taken"], row["taken"])

    def test_animated_gif_refused(self):
        gif = os.path.join(TMP, "anim.gif")
        frames = [Image.new("RGB", (40, 40), c) for c in ("red", "blue")]
        frames[0].save(gif, save_all=True, append_images=frames[1:])
        with self.assertRaises(editor.EditError):
            editor.load_source(gif)


if __name__ == "__main__":
    unittest.main()
