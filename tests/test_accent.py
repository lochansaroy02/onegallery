"""Accent colour: KDE's accent colour and the user's choice.  Run: python -m unittest discover -s tests"""

import os
import shutil
import sys
import tempfile
import unittest

TMP = tempfile.mkdtemp(prefix="onegallery-accent-test-")
os.environ.setdefault("ONEGALLERY_HOME", os.path.join(TMP, "home"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.controller import kde_accent_color  # noqa: E402
from backend.settings import Settings  # noqa: E402


def tearDownModule():
    shutil.rmtree(TMP, ignore_errors=True)


class KdeAccentTests(unittest.TestCase):
    def setUp(self):
        self.saved = os.environ.get("XDG_CONFIG_HOME")
        self.config = tempfile.mkdtemp(dir=TMP)
        os.environ["XDG_CONFIG_HOME"] = self.config

    def tearDown(self):
        if self.saved is None:
            os.environ.pop("XDG_CONFIG_HOME", None)
        else:
            os.environ["XDG_CONFIG_HOME"] = self.saved

    def write(self, text):
        with open(os.path.join(self.config, "kdeglobals"), "w") as f:
            f.write(text)

    def test_custom_or_wallpaper_accent(self):
        self.write("[General]\nAccentColor=233,84,32\nAccentColorFromWallpaper=true\n"
                   "[Colors:View]\nDecorationFocus=61,174,233\n")
        self.assertEqual(kde_accent_color(), "#e95420")

    def test_scheme_accent(self):
        self.write("[General]\nColorScheme=BreezeDark\n[Colors:View]\nDecorationFocus=61,174,233\n")
        self.assertEqual(kde_accent_color(), "#3daee9")

    def test_selection_fallback_and_missing(self):
        self.write("[Colors:Selection]\nBackgroundNormal=10,20,30\n")
        self.assertEqual(kde_accent_color(), "#0a141e")
        self.write("[General]\nAccentColor=nonsense\n")
        self.assertEqual(kde_accent_color(), "")
        os.unlink(os.path.join(self.config, "kdeglobals"))
        self.assertEqual(kde_accent_color(), "")


class AccentSettingTests(unittest.TestCase):
    def test_values(self):
        s = Settings()
        self.assertEqual(s.accent, "system")
        s.accent = "#F97316"
        self.assertEqual(s.accent, "#f97316")
        s.accent = "orange"        # rejected
        s.accent = "#12345"        # rejected
        self.assertEqual(s.accent, "#f97316")
        s.accent = "system"
        self.assertEqual(s.accent, "system")


if __name__ == "__main__":
    unittest.main()
