#!/usr/bin/env python3
"""Drive the Collections tab: Stories slideshow, Places (real GeoNames download), People.

    python tools/collections_smoke.py --faces DIR --out /tmp/onegallery-collections-shots

DIR must contain face_detection_yunet_2023mar.onnx, face_recognition_sface_2021dec.onnx,
lena.jpg and messi5.jpg (OpenCV samples); without --faces the People part is skipped.
"""
import argparse
import os
import shutil
import sys
import tempfile
import time
from datetime import date, datetime, timedelta
from fractions import Fraction
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
parser.add_argument("--faces", default="")
parser.add_argument("--out", default="collections-shots")
args = parser.parse_args()

tmp = Path(tempfile.mkdtemp(prefix="onegallery-coll-"))
os.environ["ONEGALLERY_HOME"] = str(tmp / "home")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image, ImageDraw, ImageEnhance, ImageOps  # noqa: E402
from PySide6.QtCore import QCoreApplication, QEventLoop  # noqa: E402
from PySide6.QtQml import QQmlEngine, QQmlExpression  # noqa: E402

import main  # noqa: E402
from backend import faces  # noqa: E402

OUT = Path(args.out)
OUT.mkdir(parents=True, exist_ok=True)
lib = tmp / "library"
lib.mkdir()


def dms(v):
    v = abs(v)
    d = int(v)
    m = int((v - d) * 60)
    return (Fraction(d), Fraction(m), Fraction(round(((v - d) * 60 - m) * 6000), 100))


def photo(name, when, gps=None, color=(90, 140, 200), label=""):
    exif = Image.Exif()
    exif.get_ifd(0x8769)[36867] = when.strftime("%Y:%m:%d %H:%M:%S")
    if gps:
        g = exif.get_ifd(0x8825)
        g[1], g[2] = ("N" if gps[0] >= 0 else "S"), dms(gps[0])
        g[3], g[4] = ("E" if gps[1] >= 0 else "W"), dms(gps[1])
    im = Image.blend(Image.new("RGB", (900, 600), color), Image.effect_noise((900, 600), 60).convert("RGB"), 0.2)
    ImageDraw.Draw(im).text((30, 30), label or when.strftime("%Y-%m-%d"), fill="white")
    im.save(lib / name, exif=exif, quality=90)


today = datetime.combine(date.today(), datetime.min.time()).replace(hour=11)
palette = [(220, 120, 80), (80, 160, 120), (120, 100, 200), (200, 170, 60), (70, 140, 200)]
for years in (1, 3):
    for k in range(6):
        when = today.replace(year=today.year - years) + timedelta(days=k - 3, hours=k)
        photo(f"memory_{years}y_{k}.jpg", when, color=palette[k % 5], label=f"{years} years ago #{k}")
for i, (city, gps) in enumerate([("lisbon", (38.7223, -9.1393)), ("lisbon2", (38.71, -9.14)),
                                 ("paris", (48.8566, 2.3522)), ("tokyo", (35.6762, 139.6503)),
                                 ("porto", (41.1579, -8.6291))]):
    photo(f"trip_{city}.jpg", today - timedelta(days=200 + i * 30), gps=gps, color=palette[i])
if args.faces:
    for name, scale in (("lena", 1.0), ("messi5", 2.0)):
        im = Image.open(os.path.join(args.faces, f"{name}.jpg")).convert("RGB")
        im = im.resize((int(im.width * scale), int(im.height * scale)))
        for i, v in enumerate([im, ImageOps.mirror(im), ImageEnhance.Brightness(im).enhance(0.85),
                               ImageEnhance.Contrast(im).enhance(1.25)]):
            v.save(lib / f"face_{name}_{i}.jpg", quality=92)

app, engine, gallery = main.create_app([sys.argv[0]])
root = engine.rootObjects()[0]
root.setProperty("width", 1200)
root.setProperty("height", 820)
coll = engine.rootContext().contextProperty("collections")
fails = []


def js(code):
    e = QQmlExpression(QQmlEngine.contextForObject(root), root, code)
    v = e.evaluate()
    if e.hasError():
        print("JS ERROR", code, e.error().toString())
        fails.append(code)
    return v[0] if isinstance(v, tuple) else v


def pump(ms):
    end = time.time() + ms / 1000
    while time.time() < end:
        QCoreApplication.processEvents(QEventLoop.AllEvents, 20)
        time.sleep(0.005)


def wait(pred, timeout=60):
    end = time.time() + timeout
    while time.time() < end:
        pump(50)
        if pred():
            return True
    return False


def check(name, ok):
    print(("PASS " if ok else "FAIL ") + name)
    if not ok:
        fails.append(name)


def shot(name, settle=800):
    pump(settle)
    root.grabWindow().save(str(OUT / f"{name}.png"))


gallery.addFolder(str(lib))
wait(lambda: not gallery.scanning and gallery.photos.itemCount > 0 and not gallery.photos.loading)
js("goTab(3)")
check("two stories (1 and 3 years ago)", wait(lambda: len(coll.property("stories")) == 2, 15))
check("places waiting for place names", wait(lambda: coll.property("placesState") == "need-data", 15))
check("people off by default", coll.property("peopleState") in ("off", "unavailable"))
shot("c1-collections-initial")

js("collections.downloadPlaceNames()")
check("real GeoNames download + lookup", wait(lambda: coll.property("placesState") == "ready"
                                              and len(coll.property("places")) >= 4, 120))
names = sorted(p["place"] for p in coll.property("places"))
print("   places:", names)
check("Lisbon grouped (2 pictures)", any(p["place"] == "Lisbon" and p["count"] == 2 for p in coll.property("places")))

if args.faces:
    faces.MODELS_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy(os.path.join(args.faces, "face_detection_yunet_2023mar.onnx"), faces.model_path("detector"))
    shutil.copy(os.path.join(args.faces, "face_recognition_sface_2021dec.onnx"), faces.model_path("recognizer"))
    js("collections.enablePeople()")
    check("people found", wait(lambda: coll.property("peopleState") == "ready" and len(coll.property("people")) == 2, 120))
shot("c2-collections-ready", 1500)

if args.faces:
    pid = coll.property("people")[0]["id"]
    js(f"openPerson({pid}, '')")
    pump(900)
    check("person album has 4 pictures", wait(lambda: gallery.albumPhotos.itemCount == 4, 10))
    js(f"collections.renamePerson({pid}, 'Lena')")
    check("rename", wait(lambda: any(p["name"] == "Lena" for p in coll.property("people")), 10))
    js("stack.currentItem.title = 'Lena'")
    shot("c3-person-album", 1200)
    js("goBack()")
    pump(500)
    js("openPeople()")
    shot("c4-people-page", 1200)
    js("goBack()")
    pump(500)

js("openPlaces()")
shot("c5-places-page", 1200)
js("goBack()")
pump(400)
key = next(p["key"] for p in coll.property("places") if p["place"] == "Lisbon")
js(f"openPlace({key!r}, 'Lisbon')")
check("place album", wait(lambda: gallery.albumPhotos.itemCount == 2, 10))
js("goBack()")
pump(500)

# start it from the event loop like a click does (a synchronous call from Python would
# hold the GIL while QML waits on the image threads)
js("Qt.callLater(function() { playStory(collections.stories[0]) })")
pump(2500)
shot("c6-story-playing", 300)
check("story playing", js("storyPlayer.visible") is True and js("storyPlayer.index") == 0)
js("storyPlayer.next()")
pump(400)
check("next slide", js("storyPlayer.index") == 1)
js("storyPlayer.togglePause()")
v1 = js("storyPlayer.index")
pump(6000)
check("paused story stays on its slide", js("storyPlayer.index") == v1)
js("storyPlayer.togglePause()")
check("story advances by itself", wait(lambda: js("storyPlayer.index") == v1 + 1, 8))
js("goBack()")
check("Esc closes the story", wait(lambda: js("storyPlayer.visible") is False, 3))

js("prefs.theme = 'dark'; goTab(3)")
shot("c7-collections-dark", 1500)
js("prefs.theme = 'system'")
print("FAILURES:", fails or "none")
coll.shutdown()
gallery.shutdown()
shutil.rmtree(tmp, ignore_errors=True)
sys.exit(1 if fails else 0)
