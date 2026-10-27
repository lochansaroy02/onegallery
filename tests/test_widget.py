"""Plasma Memories widget feed.  Run: python -m unittest discover -s tests"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path

TMP = tempfile.mkdtemp(prefix="onegallery-widget-test-")
os.environ.setdefault("ONEGALLERY_HOME", os.path.join(TMP, "home"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from PIL import Image  # noqa: E402

from backend import db, scanner, widget  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TODAY = date.today()


def tearDownModule():
    shutil.rmtree(TMP, ignore_errors=True)


def photo(path, when: datetime, size=(1600, 1200), orientation=None):
    exif = Image.Exif()
    exif.get_ifd(0x8769)[36867] = when.strftime("%Y:%m:%d %H:%M:%S")
    if orientation:
        exif[0x0112] = orientation
    Image.effect_noise(size, 40).convert("RGB").save(path, exif=exif, quality=90)


def years_ago(years: int) -> datetime:
    try:
        day = TODAY.replace(year=TODAY.year - years)
    except ValueError:  # 29 February
        day = TODAY.replace(year=TODAY.year - years, day=28)
    return datetime(day.year, day.month, day.day, 12, 0)


class FeedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.init()
        cls.lib = os.path.join(TMP, "lib")
        os.makedirs(cls.lib)
        cls.memory = os.path.join(cls.lib, "two_years_ago.jpg")
        photo(cls.memory, years_ago(2))
        cls.rotated = os.path.join(cls.lib, "rotated_recent.jpg")
        photo(cls.rotated, datetime.now(), orientation=6)   # stored landscape, shown portrait
        cls.old = os.path.join(cls.lib, "old_favorite.jpg")
        photo(cls.old, years_ago(9).replace(month=(TODAY.month + 5) % 12 + 1, day=10))
        cls.broken = os.path.join(cls.lib, "broken.jpg")
        photo(cls.broken, years_ago(3).replace(month=(TODAY.month + 5) % 12 + 1, day=12))
        scanner.scan_root({"path": cls.lib, "mount": "/"}, min_size_kb=0)
        with open(cls.broken, "wb") as f:   # corrupted after it was indexed
            f.write(b"\xff\xd8not really a jpeg")
        conn = db.connect()
        with conn:
            conn.execute("UPDATE images SET favorite = 1 WHERE path = ?", (cls.old,))

    def test_lists_and_images(self):
        feed = widget.build_feed(TODAY)
        on_disk = json.loads(widget.FEED_PATH.read_text(encoding="utf-8"))
        self.assertEqual(on_disk, feed)
        self.assertEqual(feed["version"], 1)
        self.assertEqual(feed["day"], TODAY.isoformat())

        memories = feed["lists"]["memories"]
        self.assertEqual([i["path"] for i in memories], [self.memory])
        self.assertEqual(memories[0]["title"], "2 years ago")
        self.assertEqual([i["path"] for i in feed["lists"]["favorites"]], [self.old])
        recent = [i["path"] for i in feed["lists"]["recent"]]
        self.assertEqual(recent[0], self.rotated)
        self.assertNotIn(self.broken, recent)   # unreadable files are left out, not fatal

        for items in feed["lists"].values():
            for item in items:
                image = Path(item["image"])
                self.assertTrue(image.is_file())
                self.assertEqual(image.parent, widget.IMAGE_DIR)
                with Image.open(image) as im:
                    self.assertLessEqual(max(im.size), widget.IMAGE_EDGE)

        rotated = next(i for i in feed["lists"]["recent"] if i["path"] == self.rotated)
        with Image.open(rotated["image"]) as im:
            self.assertGreater(im.height, im.width)   # EXIF orientation applied

    def test_rebuild_reuses_and_cleans_up(self):
        widget.build_feed(TODAY)
        stale = widget.IMAGE_DIR / "0123456789abcdef0123_1-1.jpg"
        stale.write_bytes(b"old")
        before = {p.name: p.stat().st_mtime_ns for p in widget.IMAGE_DIR.iterdir()}
        widget.build_feed(TODAY)
        after = {p.name: p.stat().st_mtime_ns for p in widget.IMAGE_DIR.iterdir()}
        self.assertNotIn(stale.name, after)
        for name, mtime in after.items():
            self.assertEqual(before[name], mtime)   # not rendered again

    def test_in_use(self):
        config = Path(TMP) / "xdg-config"
        config.mkdir(exist_ok=True)
        old = os.environ.get("XDG_CONFIG_HOME")
        os.environ["XDG_CONFIG_HOME"] = str(config)
        try:
            self.assertFalse(widget.in_use())
            appletsrc = config / "plasma-org.kde.plasma.desktop-appletsrc"
            appletsrc.write_text("[Containments][1][Applets][7]\nplugin=org.kde.plasma.digitalclock\n")
            self.assertFalse(widget.in_use())
            appletsrc.write_text(appletsrc.read_text() + "[Containments][1][Applets][9]\n"
                                 "plugin=org.kde.onegallery.memories\n")
            self.assertTrue(widget.in_use())
        finally:
            if old is None:
                os.environ.pop("XDG_CONFIG_HOME")
            else:
                os.environ["XDG_CONFIG_HOME"] = old

    def test_command_line(self):
        env = dict(os.environ, ONEGALLERY_HOME=os.path.join(TMP, "cli-home"))
        result = subprocess.run([sys.executable, str(ROOT / "main.py"), "--widget-feed"],
                                env=env, capture_output=True, text=True, timeout=120)
        self.assertEqual(result.returncode, 0, result.stderr)
        feed_path = Path(result.stdout.strip())
        self.assertEqual(feed_path.name, "feed.json")
        feed = json.loads(feed_path.read_text(encoding="utf-8"))
        self.assertEqual(feed["lists"], {"memories": [], "favorites": [], "recent": []})


class PackageTests(unittest.TestCase):
    PLASMOID = ROOT / "packaging" / "plasmoid" / widget.PLUGIN_ID

    def test_metadata(self):
        meta = json.loads((self.PLASMOID / "metadata.json").read_text(encoding="utf-8"))
        self.assertEqual(meta["KPlugin"]["Id"], widget.PLUGIN_ID)
        self.assertEqual(meta["KPackageStructure"], "Plasma/Applet")
        for part in ("ui/main.qml", "ui/MemoryFrame.qml", "ui/configGeneral.qml",
                     "config/config.qml", "config/main.xml"):
            self.assertTrue((self.PLASMOID / "contents" / part).is_file(), part)

    def test_config_keys_match(self):
        import re
        xml = (self.PLASMOID / "contents" / "config" / "main.xml").read_text(encoding="utf-8")
        keys = set(re.findall(r'<entry name="(\w+)"', xml))
        page = (self.PLASMOID / "contents" / "ui" / "configGeneral.qml").read_text(encoding="utf-8")
        self.assertEqual(set(re.findall(r"property \w+(?: \w+)? cfg_(\w+)", page)), keys)
        main = (self.PLASMOID / "contents" / "ui" / "main.qml").read_text(encoding="utf-8")
        self.assertTrue(set(re.findall(r"Plasmoid\.configuration\.(\w+)", main)) <= keys)


if __name__ == "__main__":
    unittest.main()
