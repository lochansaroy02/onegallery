#!/usr/bin/env python3
"""Drive the viewer's ⋮ menu (themed menu, Set as ▸, Print…) and the print sheet.

    QT_QPA_PLATFORM=offscreen python tools/viewer_menu_smoke.py --out /tmp/onegallery-menu-shots

Set as is checked for presence only here (it would change this machine's wallpaper);
tests/test_desktop.py covers the commands it runs. Printing goes to "Save as PDF".
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
parser.add_argument("--out", default="menu-shots")
args = parser.parse_args()

tmp = Path(tempfile.mkdtemp(prefix="onegallery-vmenu-"))
os.environ["ONEGALLERY_HOME"] = str(tmp / "home")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image  # noqa: E402
from PySide6.QtCore import QCoreApplication, QEventLoop, QPoint, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtQml import QQmlEngine, QQmlExpression  # noqa: E402

import main  # noqa: E402
from backend import desktop  # noqa: E402

OUT = Path(args.out)
OUT.mkdir(parents=True, exist_ok=True)
lib = tmp / "library"
lib.mkdir()
now = datetime.now()
for i, color in enumerate([(220, 120, 80), (80, 160, 120)]):
    exif = Image.Exif()
    exif.get_ifd(0x8769)[36867] = (now - timedelta(hours=i + 1)).strftime("%Y:%m:%d %H:%M:%S")
    im = Image.blend(Image.effect_noise((1200, 800), 50).convert("RGB"), Image.new("RGB", (1200, 800), color), 0.6)
    im.save(lib / f"p{i}.jpg", exif=exif, quality=90)
has_video = bool(shutil.which("ffmpeg"))
if has_video:
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=25", "-t", "3",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(lib / "v.mp4")], check=True)
    os.utime(lib / "v.mp4", ((now - timedelta(days=2)).timestamp(),) * 2)

app, engine, gallery = main.create_app([sys.argv[0]])
root = engine.rootObjects()[0]
root.setProperty("width", 1100)
root.setProperty("height", 780)
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


def shot(name, settle=600):
    pump(settle)
    root.grabWindow().save(str(OUT / f"{name}.png"))


def visible_items(ref):
    return json.loads(js(f"""(function() {{ var m = {ref}; var out = [];
        for (var i = 0; i < m.count; ++i) {{ var it = m.itemAt(i); if (it && it.visible && it.text) out.push(it.text) }}
        return JSON.stringify(out) }})()"""))


total = 3 if has_video else 2
gallery.addFolder(str(lib))
wait(lambda: not gallery.scanning and gallery.photos.itemCount == total and not gallery.photos.loading)
# helper to reach the menu object from JS
js("Qt.callLater(function() { openViewer(currentGrid, 0) })")
check("viewer open", wait(lambda: js("viewer.visible") is True, 5))
pump(800)
moreMenuRef = "viewer.moreMenu"
check("menu found", js(f"{moreMenuRef} !== null") is True)
js(f"{moreMenuRef}.popup(viewer, viewer.width - 300, 60)")
pump(400)
texts = visible_items(moreMenuRef)
print("   items:", texts)
check("Set as and Print offered for a picture", "Set as" in texts and "Print…" in texts)
js(f"{moreMenuRef}.close()")
pump(300)
# a real right-click on the picture opens the menu at the pointer
QTest.mouseClick(root, Qt.RightButton, Qt.NoModifier, QPoint(300, 260))
check("right-click opens the menu", wait(lambda: js(f"{moreMenuRef}.opened") is True, 3))
check("menu at the pointer", abs(js(f"{moreMenuRef}.x") - 300) <= 2 and abs(js(f"{moreMenuRef}.y") - 260) <= 2)
shot("m0-right-click", 400)
js(f"{moreMenuRef}.close()")
pump(300)
QTest.mouseClick(root, Qt.RightButton, Qt.NoModifier, QPoint(1080, 760))
check("menu kept inside the window near an edge", wait(lambda: js(f"{moreMenuRef}.opened") is True, 3)
      and js(f"{moreMenuRef}.x + {moreMenuRef}.width") <= 1100 and js(f"{moreMenuRef}.y + {moreMenuRef}.height") <= 780)
check("picture stays open (no zoom / chrome toggle side effects)", js("viewer.visible") is True)
js(f"{moreMenuRef}.close()")
pump(300)
js(f"{moreMenuRef}.popup(viewer, viewer.width - 300, 60)")
pump(300)
check("themed menu (StyledMenu background)", js(f"{moreMenuRef}.background.radius") > 0)
check("rows have icons", js(f"(function() {{ var m = {moreMenuRef}; for (var i = 0; i < m.count; ++i) {{ var it = m.itemAt(i); if (it && it.text === 'Details') return it.iconName }} return '' }})()") == "info")
shot("m1-viewer-menu-light")
js(f"{moreMenuRef}.setAsMenu.popup(viewer, viewer.width - 590, 200)")
pump(300)
shot("m2-set-as", 300)
js(f"{moreMenuRef}.setAsMenu.close(); {moreMenuRef}.close()")
js("prefs.theme = 'dark'")
pump(300)
js(f"{moreMenuRef}.popup(viewer, viewer.width - 300, 60)")
shot("m3-viewer-menu-dark")
js(f"{moreMenuRef}.close(); prefs.theme = 'system'")
pump(300)

if has_video:
    js("viewer.goTo(2)")
    pump(800)
    js(f"{moreMenuRef}.popup(viewer, viewer.width - 300, 60)")
    pump(300)
    vt = visible_items(moreMenuRef)
    print("   video items:", vt)
    check("no Set as / Print for a video", "Set as" not in vt and "Print…" not in vt and "Play video" in vt)
    js(f"{moreMenuRef}.close(); viewer.goTo(0)")
    pump(600)

# Ctrl+Shift+B / Ctrl+Shift+L: set as wallpaper / lock screen (recorded, not applied)
applied = []
desktop.apply = lambda path, target: applied.append((os.path.basename(path), target)) or target
js("viewer.forceActiveFocus()")
QTest.keyClick(root, Qt.Key_B, Qt.ControlModifier | Qt.ShiftModifier)
check("Ctrl+Shift+B sets the wallpaper", wait(lambda: ("p0.jpg", "wallpaper") in applied, 5))
QTest.keyClick(root, Qt.Key_L, Qt.ControlModifier | Qt.ShiftModifier)
check("Ctrl+Shift+L sets the lock screen", wait(lambda: ("p0.jpg", "lockscreen") in applied, 5))
check("toast confirms", wait(lambda: js("toast.visible") is True, 3))
if has_video:
    js("viewer.goTo(2)")
    pump(800)
    before = len(applied)
    QTest.keyClick(root, Qt.Key_B, Qt.ControlModifier | Qt.ShiftModifier)
    pump(600)
    check("shortcuts do nothing on a video", len(applied) == before)
    js("viewer.goTo(0)")
    pump(600)

# File > Print… (Ctrl+P) opens the print sheet
js("Qt.callLater(function() { printPicture(viewer.info) })")
check("print sheet open", wait(lambda: js("printDialog.opened") is True, 5))
check("printers listed (Save as PDF last)", wait(lambda: js("printDialog.loading") is False, 15)
      and js("printDialog.printers[printDialog.printers.length - 1].pdf") is True)
check("auto landscape for a wide picture", js("printDialog.landscape") is True)
shot("m4-print-sheet", 900)
js("printDialog.scaling = 'fill'; printDialog.gray = true; printDialog.paper = '10x15'")
shot("m5-print-sheet-options", 700)
pdf = tmp / "out.pdf"
js(f"printDialog.printerIndex = printDialog.printers.length - 1; printDialog.pdfPath = {json.dumps(str(pdf))}")
js("printDialog.start()")
check("PDF written", wait(lambda: pdf.exists() and pdf.stat().st_size > 10_000, 20))
check("print sheet closed", js("printDialog.opened") is False)
js("prefs.theme = 'dark'")
js("Qt.callLater(function() { printPicture(viewer.info) })")
wait(lambda: js("printDialog.opened") is True and js("printDialog.loading") is False, 10)
shot("m6-print-sheet-dark", 900)
js("printDialog.close(); prefs.theme = 'system'")

print("FAILURES:", fails or "none")
gallery.shutdown()
shutil.rmtree(tmp, ignore_errors=True)
sys.exit(1 if fails else 0)
