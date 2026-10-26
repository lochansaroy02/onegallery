"""Videos: metadata, posters, indexing next to photos.  Run: python -m unittest discover -s tests"""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from unittest import mock

TMP = tempfile.mkdtemp(prefix="onegallery-video-test-")
os.environ.setdefault("ONEGALLERY_HOME", os.path.join(TMP, "home"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from PIL import Image  # noqa: E402

from backend import db, is_video, scanner, supported_exts, thumbs, video  # noqa: E402
from backend.models import build_filter, query_items, F_DUR, F_PATH, F_VIDEO  # noqa: E402

HAVE_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))
RECORDED = datetime(2023, 6, 15, 10, 20, 30, tzinfo=timezone.utc)


def tearDownModule():
    shutil.rmtree(TMP, ignore_errors=True)


def ffmpeg(*args):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)


class PureTests(unittest.TestCase):
    def test_extensions(self):
        self.assertIn(".mp4", supported_exts())
        self.assertIn(".mkv", supported_exts())
        self.assertTrue(is_video("/x/Clip.MOV"))
        self.assertFalse(is_video("/x/a.jpg"))

    def test_format_duration(self):
        self.assertEqual(video.format_duration(0), "0:00")
        self.assertEqual(video.format_duration(7.4), "0:07")
        self.assertEqual(video.format_duration(272), "4:32")
        self.assertEqual(video.format_duration(3723), "1:02:03")

    def test_dates_and_locations(self):
        self.assertEqual(video.parse_iso_date("2023-06-15T10:20:30.000000Z"), int(RECORDED.timestamp()))
        self.assertEqual(video.parse_iso_date("2023-06-15T12:20:30+0200"), int(RECORDED.timestamp()))
        self.assertIsNone(video.parse_iso_date("1970-01-01T00:00:00.000000Z"))  # never set
        self.assertIsNone(video.parse_iso_date("garbage"))
        self.assertEqual(video.parse_location("+38.7223-009.1393/"), (38.7223, -9.1393))
        self.assertEqual(video.parse_location("+37.3318-122.0312+010.000/"), (37.3318, -122.0312))
        self.assertEqual(video.parse_location("+00.0000+000.0000/"), (None, None))

    def test_placeholder_is_not_cached(self):
        path = os.path.join(TMP, "fake.mp4")
        with open(path, "wb") as f:
            f.write(b"\0" * 1000)
        out = thumbs.cache_path(path, "1-1")
        with mock.patch.object(video, "FFMPEG", None):
            im = thumbs.make_thumbnail(path, out)
        self.assertEqual(min(im.size), thumbs.THUMB_SHORT_SIDE)
        self.assertFalse(out.exists())


@unittest.skipUnless(HAVE_FFMPEG, "ffmpeg / ffprobe not installed")
class VideoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.init()
        cls.root = os.path.join(TMP, "Videos")
        os.makedirs(cls.root)
        cls.mp4 = os.path.join(cls.root, "clip.mp4")
        ffmpeg("-f", "lavfi", "-i", "testsrc2=size=640x360:rate=25", "-f", "lavfi", "-i", "sine",
               "-t", "4", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
               "-metadata", "creation_time=2023-06-15T10:20:30Z", cls.mp4)
        # rotated phone video: stored 640x360, displayed 360x640
        cls.mov = os.path.join(cls.root, "phone.mov")
        ffmpeg("-display_rotation", "90", "-i", cls.mp4, "-c", "copy",
               "-metadata", "location=+38.7223-009.1393/", cls.mov)
        cls.webm = os.path.join(cls.root, "screen.webm")
        ffmpeg("-f", "lavfi", "-i", "testsrc=size=320x240:rate=25", "-t", "2", "-c:v", "libvpx-vp9", cls.webm)
        cls.jpg = os.path.join(cls.root, "photo.jpg")
        exif = Image.Exif()
        exif.get_ifd(0x8769)[36867] = "2023:06:15 11:00:00"   # local time, between the videos
        Image.effect_noise((400, 300), 40).convert("RGB").save(cls.jpg, exif=exif)
        os.utime(cls.webm, (RECORDED.timestamp() - 86400, RECORDED.timestamp() - 86400))
        cls.broken = os.path.join(cls.root, "broken.mkv")
        with open(cls.broken, "wb") as f:
            f.write(os.urandom(30_000))
        cls.stats = scanner.scan_root({"path": cls.root, "mount": "/"}, min_size_kb=0)

    def test_probe(self):
        m = video.probe(self.mp4)
        self.assertEqual((m.width, m.height), (640, 360))
        self.assertAlmostEqual(m.duration, 4.0, delta=0.1)
        self.assertEqual(m.taken, int(RECORDED.timestamp()))
        r = video.probe(self.mov)
        self.assertEqual((r.width, r.height), (360, 640))

    def test_mp4_reader_without_ffprobe(self):
        m = video._mp4(self.mp4)
        self.assertEqual((m.width, m.height, m.taken), (640, 360, int(RECORDED.timestamp())))
        self.assertAlmostEqual(m.duration, 4.0, delta=0.1)
        r = video._mp4(self.mov)
        self.assertEqual((r.width, r.height), (360, 640))
        self.assertEqual((r.lat, r.lon), (38.7223, -9.1393))
        with mock.patch.object(video, "FFPROBE", None):
            self.assertEqual(video.probe(self.webm).width, 0)       # unknown container: kept
            self.assertEqual(video.probe(self.mp4).width, 640)      # MP4: read from the file

    def test_scan_indexes_videos(self):
        self.assertEqual(self.stats["errors"], 1)  # the broken .mkv is skipped
        rows = {os.path.basename(r[0]): r[1:] for r in db.connect().execute(
            "SELECT path, video, duration, width, height FROM images WHERE root = ?", (self.root,))}
        self.assertEqual(set(rows), {"clip.mp4", "phone.mov", "screen.webm", "photo.jpg"})
        self.assertEqual(rows["clip.mp4"][:1], (1,))
        self.assertEqual(rows["phone.mov"][2:], (360, 640))
        self.assertEqual(rows["photo.jpg"][:2], (0, 0))

    def test_models(self):
        where, params = build_filter("root", self.root)
        items = query_items(where, params)
        names = [os.path.basename(it[F_PATH]) for it in items]
        # newest first, videos and photos mixed by date; the webm falls back to its mtime
        self.assertEqual(names[-1], "screen.webm")
        self.assertEqual(sum(it[F_VIDEO] for it in items), 3)
        where, params = build_filter("videos", "")
        vids = {os.path.basename(it[F_PATH]): it for it in query_items(where, params)
                if it[F_PATH].startswith(self.root)}
        self.assertEqual(set(vids), {"clip.mp4", "phone.mov", "screen.webm"})
        self.assertAlmostEqual(vids["clip.mp4"][F_DUR], 4.0, delta=0.1)
        where, params = build_filter("search", "video")
        self.assertIn(self.mp4, [it[F_PATH] for it in query_items(where, params)])

    def test_capture_frame(self):
        self.assertEqual(video.capture_name("/v/clip.mp4", 83456), "clip_frame_01-23-456.jpg")
        self.assertEqual(video.capture_name("/v/clip.mp4", 3723000), "clip_frame_1-02-03-000.jpg")
        out_dir = os.path.join(TMP, "captures")
        os.makedirs(out_dir, exist_ok=True)
        taken = int(RECORDED.timestamp())
        first = video.save_frame(self.mp4, 2000, out_dir, taken)
        second = video.save_frame(self.mp4, 2000, out_dir, taken)   # same moment: new name
        self.assertNotEqual(first, second)
        with Image.open(first) as im:
            self.assertEqual(im.size, (640, 360))
        meta = scanner.read_metadata(first, 0)
        self.assertEqual(meta.taken, taken + 2)   # dated at that moment of the recording
        with Image.open(video.save_frame(self.mov, 1000, out_dir, None)) as im:
            self.assertEqual(im.size, (360, 640))  # rotation applied
        end = video.save_frame(self.mp4, 4000, out_dir, taken)      # the very end still works
        self.assertTrue(os.path.exists(end))
        with mock.patch.object(video, "FFMPEG", None):
            with self.assertRaises(RuntimeError):
                video.frame_at(self.mp4, 0)

    def test_thumbnail_and_full(self):
        out = thumbs.cache_path(self.mov, "t")
        im = thumbs.make_thumbnail(self.mov, out)
        self.assertTrue(out.exists())
        self.assertGreater(im.height, im.width)   # rotation applied
        self.assertEqual(min(im.size), thumbs.THUMB_SHORT_SIDE)
        full = thumbs.load_full(self.mp4, 1280, 1280)
        self.assertEqual(full.size, (640, 360))


if __name__ == "__main__":
    unittest.main()
