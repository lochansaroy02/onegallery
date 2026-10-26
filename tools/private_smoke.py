#!/usr/bin/env python3
"""Drive the private album like a user: set a password, move pictures and a video in,
lock, unlock (wrong, then right password), view, move out, delete, lock again.

    QT_QPA_PLATFORM=offscreen python tools/private_smoke.py --out /tmp/onegallery-private-shots
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
parser.add_argument("--out", default="private-shots")
args = parser.parse_args()

tmp = Path(tempfile.mkdtemp(prefix="onegallery-psmoke-"))
os.environ["ONEGALLERY_HOME"] = str(tmp / "home")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image  # noqa: E402
from PySide6.QtCore import QCoreApplication, QEventLoop, QPoint, Qt  # noqa: E402
from PySide6.QtQml import QQmlEngine, QQmlExpression  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

import main  # noqa: E402
from backend import private  # noqa: E402

OUT = Path(args.out)
OUT.mkdir(parents=True, exist_ok=True)
lib = tmp / "library"
lib.mkdir()
now = datetime.now()
for i, color in enumerate([(220, 120, 80), (80, 160, 120), (90, 110, 210)]):
    exif = Image.Exif()
    exif.get_ifd(0x8769)[36867] = (now - timedelta(hours=i + 1)).strftime("%Y:%m:%d %H:%M:%S")
    im = Image.blend(Image.effect_noise((900, 600), 50).convert("RGB"), Image.new("RGB", (900, 600), color), 0.6)
    im.save(lib / f"p{i}.jpg", exif=exif, quality=90)
has_video = bool(shutil.which("ffmpeg"))
if has_video:
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=25", "-t", "3",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(lib / "v.mp4")], check=True)
PASSWORD = "summer-2026"

app, engine, gallery = main.create_app([sys.argv[0]])
root = engine.rootObjects()[0]
root.setProperty("width", 1000)
root.setProperty("height", 760)
album = engine.rootContext().contextProperty("privateAlbum")
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


def wait(pred, timeout=20):
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


def shot(name, settle=700):
    pump(settle)
    root.grabWindow().save(str(OUT / f"{name}.png"))


def type_text(text):
    for ch in text:
        QTest.keyClick(root, ch)
    pump(100)


def press(key, mods=Qt.NoModifier):
    QTest.keyClick(root, key, mods)
    pump(150)


total = 4 if has_video else 3
gallery.addFolder(str(lib))
wait(lambda: not gallery.scanning and gallery.photos.itemCount == total and not gallery.photos.loading)
check("private album card in Albums", any(a["kind"] == "private" for a in gallery.albums.property("entries")))

# select two pictures (and the video) and move them in: first a password is set up
paths = [str(lib / "p0.jpg"), str(lib / "p1.jpg")] + ([str(lib / "v.mp4")] if has_video else [])
js("Qt.callLater(function() { moveToPrivate(%s, null) })" % repr(paths).replace("'", '"'))
check("set-up dialog opens", wait(lambda: js("passwordDialog.opened") is True and js("passwordDialog.mode") == "create", 5))
pump(300)
type_text("abc")
check("short password refused", js("passwordDialog.valid") is False)
press(Qt.Key_A, Qt.ControlModifier)
type_text(PASSWORD)
press(Qt.Key_Return)                 # to the second field
type_text(PASSWORD + "x")
check("mismatch refused", js("passwordDialog.valid") is False)
shot("p1-setup-mismatch", 300)
press(Qt.Key_Backspace)
check("matching passwords accepted", js("passwordDialog.valid") is True)
press(Qt.Key_Return)
check("album created", wait(lambda: album.property("exists") is True, 10))
check("confirm move", wait(lambda: js("confirmDialog.opened") is True, 5))
shot("p2-confirm-move", 400)
js("confirmDialog.onAccept(); confirmDialog.close()")
check("originals removed", wait(lambda: not any(os.path.exists(p) for p in paths), 30))
check("gone from the library", wait(lambda: gallery.photos.itemCount == total - len(paths), 10))
check("album locked again (it was only unlocked to move them in)", wait(lambda: album.property("unlocked") is False, 5))
leaks = [p for p in (tmp / "home").rglob("*") if p.is_file() and p.suffix == ".jpg" and "private" not in str(p)]
check("no cached thumbnails of moved pictures left", all("p0" not in p.name and "p1" not in p.name for p in leaks))

# open it: wrong password, then the right one
js("goTab(2)")
pump(400)
js("Qt.callLater(function() { openPrivateAlbum() })")
check("unlock dialog", wait(lambda: js("passwordDialog.opened") is True and js("passwordDialog.mode") == "unlock", 5))
pump(300)
type_text("guess")
press(Qt.Key_Return)
check("wrong password rejected", wait(lambda: js("passwordDialog.error") == "Wrong password", 10))
shot("p3-wrong-password", 300)
press(Qt.Key_A, Qt.ControlModifier)
type_text(PASSWORD)
press(Qt.Key_Return)
check("unlocked and opened", wait(lambda: js("privateOpen") is True and album.property("unlocked") is True, 10))
check("items listed", wait(lambda: js("privatePhotos.itemCount") == len(paths), 10))
shot("p4-private-grid", 1500)

# view a picture: no share / edit, but move out & delete
js("Qt.callLater(function() { openViewer(currentGrid, 0) })")
check("viewer shows a private item", wait(lambda: js("viewer.visible && viewer.info.private === true") is True, 5))
pump(1500)
check("full picture decrypted", js("viewer.info.full").startswith("image://private/full/"))
js("viewer.moreMenu.popup(viewer, viewer.width - 300, 60)")
pump(300)
items = js("""(function() { var m = viewer.moreMenu; var out = [];
    for (var i = 0; i < m.count; ++i) { var it = m.itemAt(i); if (it && it.visible && it.text) out.push(it.text) }
    return JSON.stringify(out) })()""")
print("   menu:", items)
check("private menu", "Move out of private album" in items and "Delete permanently" in items
      and "Open with…" not in items and "Set as" not in items)
shot("p5-private-viewer-menu", 300)
js("viewer.moreMenu.close()")

if has_video:
    vid = next(i for i in range(len(paths)) if js(f"privatePhotos.itemAt({i}).video") is True)
    js(f"viewer.goTo({vid})")
    check("private video decrypted and plays", wait(lambda: js("viewer.preview !== null && viewer.preview.playing") is True, 20))
    temp_dirs = list(private._temp_base().glob(private.TEMP_PREFIX + "*"))
    check("decrypted copy in a private temp folder", len(temp_dirs) == 1)
    js("viewer.goTo(0)")
    pump(600)

# move one out, delete one
first_name = js("viewer.info.name")
js("viewer.moveCurrentOutOfPrivate()")
check("moved out to its folder", wait(lambda: (lib / first_name).exists(), 15))
check("back in the library", wait(lambda: gallery.photos.itemCount == total - len(paths) + 1, 15))
js("goBack()")
pump(500)
before = js("privatePhotos.itemCount")
js("Qt.callLater(function() { deletePrivate([privatePhotos.idAt(0)], null) })")
check("delete asks first", wait(lambda: js("confirmDialog.opened") is True, 5))
js("confirmDialog.onAccept(); confirmDialog.close()")
check("deleted permanently", wait(lambda: js("privatePhotos.itemCount") == before - 1, 10))

# lock: page closes, decrypted videos are removed
js("closePrivateAlbum()")
check("locked and closed", wait(lambda: album.property("unlocked") is False and js("privateOpen") is False, 5))
check("decrypted videos removed", not list(private._temp_base().glob(private.TEMP_PREFIX + "*")))
check("nothing private visible when locked", js("privatePhotos.itemCount") == 0)

js("openSettings()")
pump(600)
js("settingsView.flick.contentY = 600")
shot("p6-settings", 900)
js("goTab(0)")
js("prefs.theme = 'dark'")
js("Qt.callLater(function() { openPrivateAlbum() })")
wait(lambda: js("passwordDialog.opened") is True, 5)
shot("p7-unlock-dark", 600)
js("passwordDialog.close(); prefs.theme = 'system'")

print("FAILURES:", fails or "none")
album.shutdown()
gallery.shutdown()
shutil.rmtree(tmp, ignore_errors=True)
sys.exit(1 if fails else 0)
