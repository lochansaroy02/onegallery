"""Colour styles: Black & white (unchanged) and Material You.  Run: python -m unittest discover -s tests"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("ONEGALLERY_HOME", os.path.join(tempfile.mkdtemp(prefix="onegallery-theme-test-"), "home"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QUrl  # noqa: E402
from PySide6.QtGui import QColor, QGuiApplication  # noqa: E402
from PySide6.QtQml import QQmlComponent, QQmlEngine  # noqa: E402

from backend.settings import Settings  # noqa: E402

app = QGuiApplication.instance() or QGuiApplication([])
ROLES = ["bg", "surface", "surfaceHigh", "text", "textSecondary", "accent", "accentText", "accentSoft",
         "placeholder", "navBg", "toastBg", "switchOff", "divider"]
QML = """
import QtQuick
import "%s" as App
QtObject {
    function roles(style, dark, seed) {
        App.Theme.colorStyle = style
        App.Theme.dark = dark
        App.Theme.seedColor = seed
        var out = {}
        for (var name of %s) out[name] = App.Theme[name].toString()
        return out
    }
}
""" % (QUrl.fromLocalFile(str(ROOT / "qml")).toString(), ROLES)


class ThemeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = QQmlEngine()
        comp = QQmlComponent(cls.engine)
        comp.setData(QML.encode(), QUrl.fromLocalFile(str(ROOT / "tests" / "theme_probe.qml")))
        cls.comp = comp
        cls.obj = comp.create()
        assert cls.obj is not None, comp.errorString()
        QQmlEngine.setObjectOwnership(cls.obj, QQmlEngine.CppOwnership)

    def roles(self, style, dark, seed="#3e91ff"):
        from PySide6.QtCore import QMetaObject, Q_ARG, Q_RETURN_ARG
        result = QMetaObject.invokeMethod(self.obj, "roles", Q_RETURN_ARG("QVariant"),
                                          Q_ARG("QVariant", style), Q_ARG("QVariant", dark), Q_ARG("QVariant", seed))
        if hasattr(result, "toVariant"):   # a JS object comes back as QJSValue
            result = result.toVariant()
        return {k: QColor(v) for k, v in result.items()}

    def test_setting(self):
        s = Settings()
        self.assertEqual(s.colorStyle, "neutral")       # the pure black & white look by default
        s.colorStyle = "tinted"
        self.assertEqual(s.colorStyle, "tinted")
        s.colorStyle = "rainbow"                        # unknown values are ignored
        self.assertEqual(s.colorStyle, "tinted")
        s.colorStyle = "neutral"

    def test_nav_style_setting(self):
        s = Settings()
        self.assertEqual(s.navStyle, "solid")            # the existing bar by default
        for style in ("frosted", "clear", "solid"):
            s.navStyle = style
            self.assertEqual(s.navStyle, style)
        s.navStyle = "mirror"                            # unknown values are ignored
        self.assertEqual(s.navStyle, "solid")

    def test_glass_shader_compiled(self):
        shaders = ROOT / "qml" / "shaders"
        qsb = shaders / "liquidglass.frag.qsb"
        self.assertTrue(qsb.exists() and qsb.stat().st_size > 1000)
        self.assertGreaterEqual(qsb.stat().st_mtime, (shaders / "liquidglass.frag").stat().st_mtime - 1,
                                "liquidglass.frag changed: run qml/shaders/build.sh")

    def test_black_and_white_unchanged(self):
        light, dark = self.roles("neutral", False), self.roles("neutral", True)
        self.assertEqual(light["bg"].name(), "#f6f6f6")
        self.assertEqual(light["surface"].name(), "#ffffff")
        self.assertEqual(dark["bg"].name(), "#000000")
        self.assertEqual(dark["surface"].name(), "#1c1c1e")
        self.assertEqual(light["accent"].name(), "#3e91ff")   # the accent exactly as chosen
        self.assertEqual(self.roles("neutral", True, "#f2559a")["bg"].name(), "#000000")  # accent never tints

    def test_material_you(self):
        for seed in ("#3e91ff", "#f2559a", "#22a861"):
            hue = QColor(seed).hslHueF()
            for dark in (False, True):
                r = self.roles("tinted", dark, seed)
                for role in ("bg", "surface", "navBg", "accentSoft"):
                    self.assertGreater(r[role].hslSaturationF(), 0.05, (seed, dark, role))  # tinted...
                    self.assertAlmostEqual(r[role].hslHueF(), hue, delta=0.05)   # ...with the seed's hue (8-bit rounding near black)
                # light mode: light surfaces + dark text; dark mode: the reverse
                self.assertEqual(r["bg"].lightnessF() > 0.5, not dark)
                self.assertEqual(r["text"].lightnessF() > 0.5, dark)
                # text on the accent stays readable
                self.assertGreater(abs(r["accent"].lightnessF() - r["accentText"].lightnessF()), 0.45)

    def test_grey_seed_stays_grey(self):
        grey = self.roles("tinted", False, "#6b7280")["bg"].hslSaturationF()     # Graphite: bluish grey
        blue = self.roles("tinted", False, "#3e91ff")["bg"].hslSaturationF()
        self.assertLess(grey, blue / 3)                                           # only a faint tint
        self.assertEqual(self.roles("tinted", False, "#777777")["bg"].hslSaturationF(), 0)  # true grey: none


if __name__ == "__main__":
    unittest.main()
