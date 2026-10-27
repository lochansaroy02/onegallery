#!/usr/bin/env python3
"""Render the Plasma Memories widget's photo frame (MemoryFrame.qml) outside plasmashell:
build a real feed from generated pictures, then screenshot the frame with its caption, with
the hover buttons, in fit mode and after a cross-fade to the next picture.

    QT_QPA_PLATFORM=offscreen python tools/widget_smoke.py --out /tmp/onegallery-widget-shots
"""
import argparse
import os
import sys
import tempfile
from datetime import date, datetime
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
parser.add_argument("--out", default="widget-shots")
args = parser.parse_args()

tmp = Path(tempfile.mkdtemp(prefix="onegallery-widget-"))
os.environ["ONEGALLERY_HOME"] = str(tmp / "home")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PIL import Image, ImageDraw  # noqa: E402
from PySide6.QtCore import QPoint, QUrl  # noqa: E402
from PySide6.QtGui import QColor, QGuiApplication  # noqa: E402
from PySide6.QtQuick import QQuickView  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

from backend import db, scanner, widget  # noqa: E402

OUT = Path(args.out)
OUT.mkdir(parents=True, exist_ok=True)
FRAME = ROOT / "packaging" / "plasmoid" / widget.PLUGIN_ID / "contents" / "ui" / "MemoryFrame.qml"


def landscape(path, when, top, bottom, sun):
    """A simple sunset-like picture, so crops and fades are easy to judge."""
    w, h = 1800, 1200
    im = Image.new("RGB", (w, h))
    draw = ImageDraw.Draw(im)
    for y in range(h):
        t = y / h
        draw.line([(0, y), (w, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(top, bottom)))
    draw.ellipse([w * 0.6, h * 0.35, w * 0.6 + 260, h * 0.35 + 260], fill=sun)
    draw.polygon([(0, h), (w * 0.35, h * 0.62), (w * 0.7, h), ], fill=(25, 30, 45))
    draw.polygon([(w * 0.4, h), (w * 0.8, h * 0.55), (w, h * 0.8), (w, h)], fill=(40, 42, 60))
    exif = Image.Exif()
    exif.get_ifd(0x8769)[36867] = when.strftime("%Y:%m:%d %H:%M:%S")
    im.save(path, exif=exif, quality=90)


def years_ago(years):
    today = date.today()
    try:
        day = today.replace(year=today.year - years)
    except ValueError:
        day = today.replace(year=today.year - years, day=28)
    return datetime(day.year, day.month, day.day, 18, 30)


lib = tmp / "library"
lib.mkdir()
landscape(lib / "a.jpg", years_ago(3), (255, 140, 90), (120, 60, 140), (255, 230, 170))
landscape(lib / "b.jpg", years_ago(1), (60, 140, 230), (190, 220, 250), (255, 250, 220))
db.init()
scanner.scan_root({"path": str(lib), "mount": "/"}, min_size_kb=0)
feed = widget.build_feed()
items = feed["lists"]["memories"]
assert len(items) == 2, feed

app = QGuiApplication(sys.argv)
view = QQuickView()
view.setColor(QColor("#2b2d31"))   # roughly a dark Plasma desktop behind the widget
view.setResizeMode(QQuickView.SizeRootObjectToView)
view.resize(440, 320)
view.setSource(QUrl.fromLocalFile(str(FRAME)))
if view.status() != QQuickView.Ready:
    sys.exit("\n".join(e.toString() for e in view.errors()))
frame = view.rootObject()
frame.setProperty("items", items)
frame.setProperty("interval", 4000)
view.show()


def shot(name, wait=1300):
    QTest.qWait(wait)
    view.grabWindow().save(str(OUT / f"{name}.png"))
    print(OUT / f"{name}.png")


shot("1-caption")
QTest.mouseMove(view, QPoint(220, 160))
shot("2-hover", 500)
frame.setProperty("index", 1)   # what main.qml does on the slideshow timer or "next"
QTest.mouseMove(view, QPoint(-10, -10))
QTest.qWait(350)
view.grabWindow().save(str(OUT / "3-cross-fade.png"))
print(OUT / "3-cross-fade.png")
shot("4-second")
frame.setProperty("crop", False)
shot("5-fit", 600)
