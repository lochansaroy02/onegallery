#!/usr/bin/env python3
"""Render the Plasma Memories widget's views outside plasmashell: build a real feed from
generated pictures, then screenshot the photo frame (caption, hover buttons, cross-fade,
live tile slide, fit mode) and the live tile flip mosaic (wide and square, mid-flip).

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
UI = ROOT / "packaging" / "plasmoid" / widget.PLUGIN_ID / "contents" / "ui"


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
skies = [((30, 30, 80), (230, 120, 160)), ((20, 120, 110), (200, 240, 210)),
         ((250, 200, 80), (240, 110, 60)), ((90, 60, 160), (40, 30, 70)),
         ((150, 200, 255), (250, 250, 255)), ((200, 70, 70), (60, 20, 40)),
         ((80, 180, 90), (230, 250, 150)), ((40, 40, 40), (160, 160, 200))]
folder = tmp / "Frame folder"
folder.mkdir()
for i, (top, bottom) in enumerate(skies):
    landscape(folder / f"{i}.jpg", datetime(2021, 6, i + 1, 9, 0), top, bottom, (255, 245, 210))
db.init()
scanner.scan_root({"path": str(lib), "mount": "/"}, min_size_kb=0)
feed = widget.build_feed(folders=[str(folder)])
items = feed["lists"]["memories"]
assert len(items) == 2, feed
tiles = feed["folders"][str(folder)]
assert len(tiles) == len(skies), feed["folders"]

app = QGuiApplication(sys.argv)


def load(name, size):
    view = QQuickView()
    view.setColor(QColor("#2b2d31"))   # roughly a dark Plasma desktop behind the widget
    view.setResizeMode(QQuickView.SizeRootObjectToView)
    view.resize(*size)
    view.setSource(QUrl.fromLocalFile(str(UI / name)))
    if view.status() != QQuickView.Ready:
        sys.exit("\n".join(e.toString() for e in view.errors()))
    return view, view.rootObject()


view, frame = load("MemoryFrame.qml", (440, 320))
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
frame.setProperty("crop", True)
frame.setProperty("transition", "slide")
frame.setProperty("index", 0)
shot("6-slide-up-midway", 200)
shot("7-slide-up-done", 1200)
view.close()

for size, label in (((440, 300), "wide"), ((340, 340), "square")):
    view, mosaic = load("TileMosaic.qml", size)
    mosaic.setProperty("items", tiles)
    view.show()
    shot(f"8-mosaic-{label}", 1000)
    for step in range(1, 4):
        mosaic.setProperty("index", step)
        QTest.qWait(900)
    mosaic.setProperty("index", 4)
    shot(f"9-mosaic-{label}-flipping", 230)
    shot(f"10-mosaic-{label}-after-flips", 900)
    view.close()
