"""Moving an LGallery install over to One Gallery.  Run: python -m unittest discover -s tests"""

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

TMP = tempfile.mkdtemp(prefix="onegallery-rename-test-")
os.environ.setdefault("ONEGALLERY_HOME", os.path.join(TMP, "home"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import backend  # noqa: E402


def tearDownModule():
    shutil.rmtree(TMP, ignore_errors=True)


@unittest.skipIf(backend.IS_WINDOWS, "Linux folder layout")
class MigrateOldName(unittest.TestCase):
    """The Linux layout (also what running from source used on a Mac)."""
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(dir=TMP))
        self.config, self.data, self.cache = (self.root / d for d in ("config", "share", "cache"))
        env = {"XDG_CONFIG_HOME": str(self.config), "XDG_DATA_HOME": str(self.data),
               "XDG_CACHE_HOME": str(self.cache), "XDG_DATA_DIRS": str(self.root / "none")}
        patches = [mock.patch.dict(os.environ, env), mock.patch.object(backend, "_home", None),
                   mock.patch.object(backend, "IS_MAC", False), mock.patch.object(backend, "IS_LINUX", True),
                   mock.patch.object(backend, "CONFIG_DIR", self.config / "onegallery"),
                   mock.patch.object(backend, "DATA_DIR", self.data / "onegallery"),
                   mock.patch.object(backend, "CACHE_DIR", self.cache / "onegallery")]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def old_install(self):
        (self.config / "lgallery").mkdir(parents=True)
        (self.config / "lgallery" / "config.json").write_text('{"folders": ["/pics"]}')
        (self.data / "lgallery" / "private").mkdir(parents=True)
        (self.data / "lgallery" / "index.db").write_bytes(b"db")
        (self.data / "lgallery" / "private" / "key").write_bytes(b"secret")
        (self.cache / "lgallery" / "thumbs").mkdir(parents=True)

    def test_moves_everything_and_leaves_links(self):
        self.old_install()
        done = backend.migrate_old_name()
        self.assertEqual(len(done), 3)
        self.assertEqual((self.config / "onegallery" / "config.json").read_text(), '{"folders": ["/pics"]}')
        self.assertEqual((self.data / "onegallery" / "private" / "key").read_bytes(), b"secret")
        self.assertTrue((self.cache / "onegallery" / "thumbs").is_dir())
        # the old paths still lead to the data (the KDE wallpaper may point inside them)
        self.assertTrue((self.data / "lgallery").is_symlink())
        self.assertEqual((self.data / "lgallery" / "index.db").read_bytes(), b"db")
        self.assertEqual(backend.migrate_old_name(), [])  # only once

    def test_never_overwrites_a_new_folder(self):
        self.old_install()
        (self.data / "onegallery").mkdir(parents=True)
        (self.data / "onegallery" / "index.db").write_bytes(b"new")
        backend.migrate_old_name()
        self.assertEqual((self.data / "onegallery" / "index.db").read_bytes(), b"new")
        self.assertEqual((self.data / "lgallery" / "index.db").read_bytes(), b"db")  # left alone
        self.assertFalse((self.data / "lgallery").is_symlink())

    def test_nothing_to_do_on_a_fresh_install(self):
        self.assertEqual(backend.migrate_old_name(), [])
        self.assertFalse((self.data / "onegallery").exists())

    def test_default_viewer_follows_the_new_launcher(self):
        self.config.mkdir(parents=True)
        mimeapps = self.config / "mimeapps.list"
        mimeapps.write_text("[Default Applications]\nimage/jpeg=lgallery.desktop;\n"
                            "image/png=org.kde.gwenview.desktop;\n\n"
                            "[Added Associations]\nimage/jpeg=lgallery.desktop;org.kde.gwenview.desktop;\n")
        backend.migrate_old_name()  # the new launcher isn't installed yet: leave it
        self.assertIn("=lgallery.desktop;", mimeapps.read_text())
        (self.data / "applications").mkdir(parents=True)
        (self.data / "applications" / "onegallery.desktop").write_text("[Desktop Entry]\n")
        backend.migrate_old_name()
        text = mimeapps.read_text()
        self.assertNotIn("lgallery.desktop", text)
        self.assertIn("image/jpeg=onegallery.desktop;\n", text)
        self.assertIn("image/png=org.kde.gwenview.desktop;", text)
        self.assertIn("image/jpeg=onegallery.desktop;org.kde.gwenview.desktop;", text)

    def test_skipped_for_test_and_sample_homes(self):
        self.old_install()
        with mock.patch.object(backend, "_home", str(self.root)):
            self.assertEqual(backend.migrate_old_name(), [])
        self.assertTrue((self.data / "lgallery").is_dir())


@unittest.skipIf(backend.IS_WINDOWS, "Mac folder layout")
class MigrateToMacLibrary(unittest.TestCase):
    """On a Mac, a library from running the source (Linux-style folders) moves into ~/Library."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(dir=TMP))
        self.config, self.data, self.cache = (self.root / d for d in ("config", "share", "cache"))
        self.support = self.root / "Library" / "Application Support" / "One Gallery"
        self.caches = self.root / "Library" / "Caches" / "One Gallery"
        env = {"XDG_CONFIG_HOME": str(self.config), "XDG_DATA_HOME": str(self.data),
               "XDG_CACHE_HOME": str(self.cache)}
        patches = [mock.patch.dict(os.environ, env), mock.patch.object(backend, "_home", None),
                   mock.patch.object(backend, "IS_MAC", True), mock.patch.object(backend, "IS_LINUX", False),
                   mock.patch.object(backend, "CONFIG_DIR", self.support),
                   mock.patch.object(backend, "DATA_DIR", self.support),
                   mock.patch.object(backend, "CACHE_DIR", self.caches)]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def test_settings_and_library_share_one_folder(self):
        (self.config / "lgallery").mkdir(parents=True)
        (self.config / "lgallery" / "config.json").write_text("{}")
        (self.data / "lgallery" / "private").mkdir(parents=True)
        (self.data / "lgallery" / "index.db").write_bytes(b"db")
        (self.cache / "lgallery" / "thumbs").mkdir(parents=True)
        backend.migrate_old_name()
        self.assertEqual((self.support / "index.db").read_bytes(), b"db")
        self.assertEqual((self.support / "config.json").read_text(), "{}")
        self.assertTrue((self.support / "private").is_dir())
        self.assertTrue((self.caches / "thumbs").is_dir())
        self.assertTrue((self.data / "lgallery").is_symlink())
        self.assertEqual(backend.migrate_old_name(), [])  # only once

    def test_newer_onegallery_folders_win(self):
        (self.data / "lgallery").mkdir(parents=True)
        (self.data / "lgallery" / "index.db").write_bytes(b"old")
        (self.data / "onegallery").mkdir(parents=True)
        (self.data / "onegallery" / "index.db").write_bytes(b"new")
        backend.migrate_old_name()
        self.assertEqual((self.support / "index.db").read_bytes(), b"new")


if __name__ == "__main__":
    unittest.main()
