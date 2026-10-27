#!/usr/bin/env python3
"""Drive phone sync in the Folders tab with a fake KDE Connect phone (no phone needed).

    python tools/phone_smoke.py --out /tmp/onegallery-phone-shots

busctl is replaced by a fake kdeconnectd whose "phone" is a folder laid out like Android
storage. Screenshots: the first-time card, a sync in progress, the synced phone (light and
dark) and the Phones group in Settings.
"""
import argparse
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
parser.add_argument("--out", default="phone-shots")
args = parser.parse_args()

tmp = Path(tempfile.mkdtemp(prefix="onegallery-phone-"))
os.environ["ONEGALLERY_HOME"] = str(tmp / "home")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image, ImageDraw  # noqa: E402
from PySide6.QtCore import QCoreApplication, QEventLoop  # noqa: E402
from PySide6.QtQml import QQmlEngine, QQmlExpression  # noqa: E402

from backend import phone  # noqa: E402

OUT = Path(args.out)
OUT.mkdir(parents=True, exist_ok=True)
DEVICE = "5f3a9c21_b7e4"
mount = tmp / "run" / DEVICE
storage = mount / "storage" / "emulated" / "0"
pictures = tmp / "Pictures"

colors = [(220, 120, 80), (80, 160, 120), (120, 100, 200), (200, 170, 60), (70, 140, 200)]
for i in range(12):
    folder = "Camera" if i < 9 else "Screenshots"
    path = storage / "DCIM" / folder / f"{'IMG' if i < 9 else 'Screenshot'}_2026102{i % 7}_{i:04d}.jpg"
    path.parent.mkdir(parents=True, exist_ok=True)
    im = Image.blend(Image.new("RGB", (800, 600), colors[i % 5]),
                     Image.effect_noise((800, 600), 60).convert("RGB"), 0.25)  # over the 20 KB minimum
    ImageDraw.Draw(im).text((30, 30), f"phone #{i}", fill="white")
    im.save(path, quality=85)
    os.utime(path, (time.time() - (12 - i) * 3600,) * 2)

state = {"mounted": False}


def fake_busctl(cmd, timeout=30):
    method = cmd[4]
    if method == "NameHasOwner":
        return json.dumps({"type": "b", "data": [True]})
    if method == "mountAndWait":
        state["mounted"] = True
        return json.dumps({"type": "b", "data": [True]})
    if method == "unmount":
        state["mounted"] = False
        return ""
    replies = {
        "devices": ("as", [DEVICE]),
        "GetAll": ("a{sv}", {"name": {"type": "s", "data": "Galaxy S24"},
                             "type": {"type": "s", "data": "phone"},
                             "isReachable": {"type": "b", "data": True}}),
        "loadedPlugins": ("as", ["kdeconnect_sftp"]),
        "isMounted": ("b", state["mounted"]),
        "mountPoint": ("s", str(mount)),
        "getDirectories": ("a{sv}", {str(storage): {"type": "s", "data": "All files"}}),
    }
    kind, value = replies[method]
    return json.dumps({"type": kind, "data": [value]})


phone._busctl = fake_busctl
phone.supported = lambda: True
phone.phone_base_dir = lambda: str(pictures / "Phone")
phone.POLL_MS = 1000
real_copy = phone.copy_item


def slow_copy(item, dest_dir):   # slow enough to photograph the progress bar
    time.sleep(0.25)
    return real_copy(item, dest_dir)


phone.copy_item = slow_copy

import main  # noqa: E402

app, engine, gallery = main.create_app([sys.argv[0]])
root = engine.rootObjects()[0]
root.setProperty("width", 1100)
root.setProperty("height", 820)
phones = engine.rootContext().contextProperty("phones")
prefs = engine.rootContext().contextProperty("prefs")
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


def wait(pred, timeout=30):
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


def row():
    devices = phones.property("devices")
    return devices[0] if devices else None


js("goTab(4)")
check("phone found", wait(lambda: phones.property("available") and row() is not None, 15))
check("not set up yet", row() is not None and not row()["setUp"])
shot("1-first-time")

phones.setUp(DEVICE, "all")
check("syncing", wait(lambda: row()["busy"] and row()["done"] >= 3, 15))
shot("2-syncing", settle=100)

check("set up after the first sync", wait(lambda: row()["setUp"] and not row()["busy"], 30))
check("12 files imported", len(list((pictures / "Phone" / "Galaxy S24").rglob("*.jpg"))) == 12)
check("phone folder added to the library", wait(
    lambda: str(pictures / "Phone") in gallery.property("folders")[0]["path"] if gallery.property("folders") else False, 10))
check("pictures in the gallery", wait(lambda: not gallery.scanning and gallery.photos.itemCount == 12, 20))
shot("3-synced")
prefs.setProperty("theme", "dark")
shot("4-synced-dark")
prefs.setProperty("theme", "light")

js("openSettings()")
pump(800)
js("""(function() {
    var f = null
    function find(item) {
        if (!item || f) return
        if (item.hasOwnProperty("contentHeight") && item.hasOwnProperty("contentY") && item.contentHeight > 1500) { f = item; return }
        for (var i = 0; i < item.children.length; ++i) find(item.children[i])
    }
    find(contentItem)
    if (f) f.contentY = f.contentHeight * 0.42
})()""")
shot("5-settings")

gallery.shutdown()
shutil.rmtree(tmp, ignore_errors=True)
print("\nscreenshots in", OUT.resolve())
print("FAILED: " + ", ".join(fails) if fails else "ALL PASSED")
sys.exit(1 if fails else 0)
