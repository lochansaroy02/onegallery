"""Set as wallpaper / lock screen, and printing.  Run: python -m unittest discover -s tests

No real wallpaper is changed: the desktop commands are captured instead of run."""

import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

TMP = tempfile.mkdtemp(prefix="onegallery-desktop-test-")
os.environ.setdefault("ONEGALLERY_HOME", os.path.join(TMP, "home"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from PIL import Image  # noqa: E402
from PySide6.QtCore import QRectF  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402

from backend import desktop, printing  # noqa: E402

app = QGuiApplication.instance() or QGuiApplication([])


def tearDownModule():
    shutil.rmtree(TMP, ignore_errors=True)


def photo(name, size=(600, 400), orientation=None, mode="RGB"):
    path = os.path.join(TMP, name)
    im = Image.new(mode, size, (200, 100, 50, 128) if mode == "RGBA" else (200, 100, 50))
    exif = Image.Exif()
    if orientation:
        exif[274] = orientation
    im.save(path, exif=exif) if path.endswith(".jpg") else im.save(path)
    return path


class WallpaperTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        patcher = mock.patch.object(desktop, "_run", side_effect=lambda cmd: self.calls.append(cmd))
        patcher.start()
        self.addCleanup(patcher.stop)
        # never reach the real Windows APIs (they would change this PC's wallpaper)
        for name in ("_windows_desktop", "_windows_lockscreen"):
            p = mock.patch.object(desktop, name, side_effect=lambda image, n=name: self.calls.append([n, image]))
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch.object(desktop, "IS_WINDOWS", False)
        p.start()
        self.addCleanup(p.stop)

    def test_windows_calls(self):
        with mock.patch.object(desktop, "IS_WINDOWS", True):
            desktop.apply(photo("win.jpg"), "both")
        self.assertEqual([c[0] for c in self.calls], ["_windows_desktop", "_windows_lockscreen"])
        self.assertTrue(self.calls[0][1].endswith(".jpg"))

    def which(self, available):
        return mock.patch.object(desktop.shutil, "which",
                                 side_effect=lambda name: f"/usr/bin/{name}" if name in available else None)

    def test_prepare_makes_an_upright_copy(self):
        src = photo("sideways.jpg", orientation=6)
        out = desktop.prepare(src)
        self.assertTrue(out.startswith(str(desktop.WALLPAPER_DIR)))
        with Image.open(out) as im:
            self.assertEqual(im.size, (400, 600))
        self.assertEqual(desktop.prepare(src), out)   # same file, same copy
        png = desktop.prepare(photo("alpha.png", mode="RGBA"))
        self.assertTrue(png.endswith(".png"))

    def test_prune_keeps_the_newest(self):
        for i in range(desktop.KEEP + 3):
            desktop.prepare(photo(f"many{i}.jpg", size=(100 + i, 100)))
        self.assertLessEqual(len(list(desktop.WALLPAPER_DIR.iterdir())), desktop.KEEP)

    def test_kde_commands(self):
        src = photo("kde.jpg")
        with self.which({"plasma-apply-wallpaperimage", "kwriteconfig6"}):
            self.assertEqual(desktop.apply(src, "both"), "both")
        image = self.calls[0][1]
        self.assertEqual(self.calls[0], ["plasma-apply-wallpaperimage", image])
        lock = [c for c in self.calls if "kscreenlockerrc" in c]
        self.assertTrue(all(c[0] == "/usr/bin/kwriteconfig6" for c in lock))
        keys = {c[c.index("--key") + 1]: c[-1] for c in lock}
        self.assertEqual(keys["WallpaperPlugin"], "org.kde.image")
        self.assertEqual(keys["Image"], "file://" + image)
        self.assertEqual(keys["PreviewImage"], "file://" + image)
        self.assertIn("org.kde.image", lock[1])

    def test_only_one_target(self):
        src = photo("one.jpg")
        with self.which({"plasma-apply-wallpaperimage", "kwriteconfig5"}):
            desktop.apply(src, "lockscreen")
        self.assertTrue(self.calls and all("kscreenlockerrc" in c for c in self.calls))
        self.assertEqual(self.calls[0][0], "/usr/bin/kwriteconfig5")
        self.calls.clear()
        with self.which({"plasma-apply-wallpaperimage"}):
            desktop.apply(src, "wallpaper")
        self.assertEqual(len(self.calls), 1)

    def test_errors(self):
        with self.which(set()), mock.patch.object(desktop.sys, "platform", "linux"):
            with self.assertRaises(desktop.WallpaperError):
                desktop.apply(photo("none.jpg"), "wallpaper")
            with self.assertRaises(desktop.WallpaperError):
                desktop.apply(photo("none2.jpg"), "lockscreen")
        with self.assertRaises(desktop.WallpaperError):
            desktop.apply(os.path.join(TMP, "missing.jpg"), "wallpaper")
        with self.assertRaises(desktop.WallpaperError):
            desktop.apply(photo("bad.jpg"), "desk")


@unittest.skipUnless(printing.AVAILABLE, "Qt Print Support not available")
class PrintTests(unittest.TestCase):
    def test_fit_and_fill(self):
        area = QRectF(0, 0, 1000, 500)
        target, source = printing.target_rect(400, 400, area, fill=False)
        self.assertEqual((target.x(), target.width(), target.height()), (250, 500, 500))
        self.assertEqual(source, QRectF(0, 0, 400, 400))
        target, source = printing.target_rect(400, 400, area, fill=True)
        self.assertEqual(target, area)
        self.assertEqual((source.y(), source.height()), (100, 200))

    def test_printers_always_offer_pdf(self):
        found = printing.printers()
        self.assertTrue(found[-1]["pdf"])
        self.assertEqual(found[-1]["id"], printing.PDF)

    def test_pdf_output(self):
        src = photo("print.jpg", size=(1200, 800))
        for fill, gray in ((False, False), (True, True)):
            out = os.path.join(TMP, f"out-{fill}-{gray}.pdf")
            msg = printing.print_image(src, {"printer": printing.PDF, "pdfPath": out, "paper": "10x15",
                                             "fill": fill, "gray": gray, "borderless": fill})
            self.assertIn("out-", msg)
            with open(out, "rb") as f:
                self.assertEqual(f.read(4), b"%PDF")
            self.assertGreater(os.path.getsize(out), 1000)

    def test_bad_printer(self):
        with self.assertRaises(RuntimeError):
            printing.print_image(photo("p2.jpg"), {"printer": "no-such-printer-xyz"})


if __name__ == "__main__":
    unittest.main()
