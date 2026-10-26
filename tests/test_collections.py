"""Collections: GPS, places, stories, people.  Run: python -m unittest discover -s tests

The People test needs the face models; point ONEGALLERY_TEST_MODELS at a folder containing
face_detection_yunet_2023mar.onnx, face_recognition_sface_2021dec.onnx, lena.jpg and
messi5.jpg (OpenCV sample images) or it is skipped.
"""

import os
import shutil
import sys
import tempfile
import time
import unittest
from datetime import date, datetime, timedelta
from fractions import Fraction

TMP = tempfile.mkdtemp(prefix="onegallery-coll-test-")
os.environ.setdefault("ONEGALLERY_HOME", os.path.join(TMP, "home"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from PIL import Image, ImageEnhance, ImageOps  # noqa: E402

from backend import db, faces, geo, scanner, stories  # noqa: E402
from backend.models import build_filter  # noqa: E402


def tearDownModule():
    shutil.rmtree(TMP, ignore_errors=True)


def dms(value):
    value = abs(value)
    d = int(value)
    m = int((value - d) * 60)
    s = round(((value - d) * 60 - m) * 60 * 100)
    return (Fraction(d), Fraction(m), Fraction(s, 100))


def photo(path, when: datetime, gps=None, size=(320, 240)):
    exif = Image.Exif()
    exif.get_ifd(0x8769)[36867] = when.strftime("%Y:%m:%d %H:%M:%S")
    if gps:
        lat, lon = gps
        g = exif.get_ifd(0x8825)
        g[1], g[2] = ("N" if lat >= 0 else "S"), dms(lat)
        g[3], g[4] = ("E" if lon >= 0 else "W"), dms(lon)
    Image.effect_noise(size, 40).convert("RGB").save(path, exif=exif, quality=90)


class GpsAndPlacesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.init()
        cls.lib = os.path.join(TMP, "gps")
        os.makedirs(cls.lib)
        now = datetime(2024, 5, 1, 12, 0)
        photo(os.path.join(cls.lib, "lisbon.jpg"), now, gps=(38.7223, -9.1393))
        photo(os.path.join(cls.lib, "sintra.jpg"), now, gps=(38.80, -9.38))
        photo(os.path.join(cls.lib, "ocean.jpg"), now, gps=(38.7, -11.0))   # ~160 km offshore
        photo(os.path.join(cls.lib, "nogps.jpg"), now)
        scanner.scan_root({"path": cls.lib, "mount": "/"}, min_size_kb=0)
        # a tiny stand-in for the GeoNames file
        geo.GEO_DIR.mkdir(parents=True, exist_ok=True)
        rows = [("2267057", "Lisbon", "38.71667", "-9.13333", "PT"),
                ("2262963", "Sintra", "38.80097", "-9.37826", "PT"),
                ("3117735", "Madrid", "40.4165", "-3.70256", "ES")]
        with open(geo.CITIES, "w", encoding="utf-8") as f:
            for gid, name, lat, lon, cc in rows:
                f.write("\t".join([gid, name, name, "", lat, lon, "P", "PPL", cc, "", "", "", "", "",
                                   "100000", "", "", "Europe/Lisbon", "2024-01-01"]) + "\n")
            f.write("x" * 200_000 + "\n")  # pass the size sanity check

    def test_gps_read_from_exif(self):
        lat, lon = db.connect().execute(
            "SELECT lat, lon FROM images WHERE name = 'lisbon.jpg'").fetchone()
        self.assertAlmostEqual(lat, 38.7223, places=3)
        self.assertAlmostEqual(lon, -9.1393, places=3)
        self.assertIsNone(db.connect().execute(
            "SELECT lat FROM images WHERE name = 'nogps.jpg'").fetchone()[0])

    def test_places(self):
        self.assertEqual(geo.assign_places(), 3)
        rows = dict(db.connect().execute("SELECT name, place || '|' || country FROM images "
                                         "WHERE place IS NOT NULL").fetchall())
        self.assertEqual(rows["lisbon.jpg"], "Lisbon|Portugal")
        self.assertEqual(rows["sintra.jpg"], "Sintra|Portugal")
        self.assertEqual(rows["ocean.jpg"], "Portugal|Portugal")  # far from any town
        where, params = build_filter("place", "Lisbon\tPortugal")
        n = db.connect().execute(f"SELECT COUNT(*) FROM images WHERE {where}", params).fetchone()[0]
        self.assertEqual(n, 1)


class StoriesTests(unittest.TestCase):
    def test_anniversary_window(self):
        today = date(2026, 10, 23)
        self.assertEqual(stories._anniversary_years_ago(date(2025, 10, 21), today, 3), 1)
        self.assertEqual(stories._anniversary_years_ago(date(2023, 10, 26), today, 3), 3)
        self.assertIsNone(stories._anniversary_years_ago(date(2024, 10, 30), today, 3))
        self.assertIsNone(stories._anniversary_years_ago(date(2026, 10, 22), today, 3))  # this year
        # across new year and leap day
        self.assertEqual(stories._anniversary_years_ago(date(2024, 12, 30), date(2026, 1, 1), 3), 1)
        self.assertEqual(stories._anniversary_years_ago(date(2024, 2, 29), date(2027, 3, 1), 3), 3)

    def test_memories(self):
        lib = os.path.join(TMP, "memories")
        os.makedirs(lib)
        today = date.today()
        base = datetime.combine(today, datetime.min.time()).replace(hour=10)
        for years in (1, 2):
            for k in range(5):
                when = base.replace(year=base.year - years) + timedelta(days=k - 2, minutes=k)
                photo(os.path.join(lib, f"y{years}_{k}.jpg"), when)
        photo(os.path.join(lib, "burst_a.jpg"), base.replace(year=base.year - 1, hour=15))
        photo(os.path.join(lib, "burst_b.jpg"), base.replace(year=base.year - 1, hour=15, second=2))
        photo(os.path.join(lib, "other.jpg"), base.replace(year=base.year - 1) + timedelta(days=40))
        photo(os.path.join(lib, "this_year.jpg"), base)
        scanner.scan_root({"path": lib, "mount": "/"}, min_size_kb=0)
        result = {s["key"]: s for s in stories.memories(today)}
        self.assertEqual(sorted(result), [1, 2])
        self.assertEqual(result[1]["title"], "1 year ago")
        self.assertEqual(result[1]["count"], 6)     # 5 + one of the burst pair
        self.assertEqual(result[2]["count"], 5)
        self.assertTrue(result[1]["items"][0]["full"].startswith("image://full/"))


@unittest.skipUnless(os.environ.get("ONEGALLERY_TEST_MODELS") and faces.engine_available(),
                     "face models / OpenCV not available")
class PeopleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        src = os.environ["ONEGALLERY_TEST_MODELS"]
        db.init()
        faces.MODELS_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy(os.path.join(src, "face_detection_yunet_2023mar.onnx"), faces.model_path("detector"))
        shutil.copy(os.path.join(src, "face_recognition_sface_2021dec.onnx"), faces.model_path("recognizer"))
        cls.lib = os.path.join(TMP, "people")
        os.makedirs(cls.lib)
        for name, scale in (("lena", 1.0), ("messi5", 2.0)):
            im = Image.open(os.path.join(src, f"{name}.jpg")).convert("RGB")
            im = im.resize((int(im.width * scale), int(im.height * scale)))
            w, h = im.size
            variants = [im, ImageOps.mirror(im), ImageEnhance.Brightness(im).enhance(0.8),
                        ImageEnhance.Contrast(im).enhance(1.3)]
            for i, v in enumerate(variants):
                v.save(os.path.join(cls.lib, f"{name}_{i}.jpg"), quality=92)
        Image.effect_noise((400, 300), 50).convert("RGB").save(os.path.join(cls.lib, "noface.jpg"))
        scanner.scan_root({"path": cls.lib, "mount": "/"}, min_size_kb=0)

    def test_index_and_group(self):
        thread = faces.FaceIndexThread()
        result = {}
        thread.indexFinished.connect(result.update)
        thread.run()  # synchronously
        self.assertGreaterEqual(result["pictures"], 9)   # other tests share the index
        self.assertEqual(result["new_people"], 2)
        people = faces.list_people()
        self.assertEqual(sorted(p["count"] for p in people), [4, 4])
        conn = db.connect()
        for p in people:
            names = {r[0].split("_")[0] for r in conn.execute(
                "SELECT i.name FROM faces f JOIN images i ON i.id = f.image_id WHERE f.person_id = ?",
                (p["id"],))}
            self.assertEqual(len(names), 1, f"person {p['id']} mixes {names}")
        self.assertEqual(faces.face_thumbnail(int(people[0]["face"].split("/")[3])).size, (192, 192))

        # a new picture of a known person is assigned on the next run, merge + rename work
        im = Image.open(os.path.join(self.lib, "lena_0.jpg"))
        im.rotate(4, expand=False).save(os.path.join(self.lib, "lena_new.jpg"), quality=92)
        scanner.scan_root({"path": self.lib, "mount": "/"}, min_size_kb=0)
        thread = faces.FaceIndexThread()
        result = {}
        thread.indexFinished.connect(result.update)
        thread.run()
        self.assertEqual((result["pictures"], result["assigned"], result["new_people"]), (1, 1, 0))
        a, b = [p["id"] for p in faces.list_people()]
        with conn:
            conn.execute("UPDATE persons SET name = 'Ana' WHERE id = ?", (a,))
        faces.merge_people(a, b)
        people = faces.list_people()
        self.assertEqual(len(people), 1)
        self.assertEqual(people[0]["name"], "Ana")
        self.assertEqual(people[0]["count"], 9)
        where, params = build_filter("person", str(people[0]["id"]))
        n = conn.execute(f"SELECT COUNT(*) FROM images WHERE {where}", params).fetchone()[0]
        self.assertEqual(n, 9)


if __name__ == "__main__":
    unittest.main()
