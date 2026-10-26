#!/usr/bin/env python3
"""Check "Open with Gallery": start with a file, browse its folder, hand-off to a running window.

    python tools/open_with_smoke.py samples --out /tmp/onegallery-openwith-shots
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
parser.add_argument("samples")
parser.add_argument("--out", default="openwith-shots")
args = parser.parse_args()

tmp = Path(tempfile.mkdtemp(prefix="onegallery-openwith-"))
os.environ["ONEGALLERY_HOME"] = str(tmp / "home")
here = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(here))

from PySide6.QtCore import QCoreApplication, QEventLoop  # noqa: E402
from PySide6.QtQml import QQmlEngine, QQmlExpression  # noqa: E402

import main  # noqa: E402
from backend import db, external  # noqa: E402

folder = tmp / "Downloads"
src = Path(args.samples) / "Pets"
shutil.copytree(src, folder)
files = external.list_folder(str(folder))
start = files[len(files) // 2]

app, engine, gallery = main.create_app([sys.argv[0]], files=[start])
server = main.InstanceServer(gallery)
root = engine.rootObjects()[0]
root.setProperty("width", 1200)
root.setProperty("height", 820)
out = Path(args.out)
out.mkdir(parents=True, exist_ok=True)
quit_requested = []
engine.quit.connect(lambda: quit_requested.append(True))
failures, errors = [], []


def js(code):
    expr = QQmlExpression(QQmlEngine.contextForObject(root), root, code)
    value = expr.evaluate()
    if expr.hasError():
        errors.append(f"{code}: {expr.error().toString()}")
    return value[0] if isinstance(value, tuple) else value


def pump(ms):
    end = time.time() + ms / 1000
    while time.time() < end:
        QCoreApplication.processEvents(QEventLoop.AllEvents, 20)
        time.sleep(0.005)


def wait(pred, timeout=20):
    end = time.time() + timeout
    while time.time() < end:
        pump(40)
        if pred():
            return True
    return False


def check(name, ok):
    print(("PASS " if ok else "FAIL ") + name)
    if not ok:
        failures.append(name)


check("viewer opens on the clicked picture", wait(lambda: js("viewer.info.path") == start))
check("whole folder is listed", wait(lambda: gallery.externalPhotos.itemCount == len(files)))
pump(600)
root.grabWindow().save(str(out / "o1-opened.png"))
check("index position matches the folder order", js("viewer.currentIndex") == files.index(start))

js("viewer.go(1)")
pump(500)
check("right arrow shows the next file in the folder", js("viewer.info.path") == files[files.index(start) + 1])
js("viewer.go(-1); viewer.go(-1)")
pump(500)
check("left arrow shows the previous file", js("viewer.info.path") == files[files.index(start) - 1])
check("folder was NOT added to the library",
      db.connect().execute("SELECT COUNT(*) FROM images").fetchone()[0] == 0 and not gallery.hasFolders)
check("favorite hidden for outside pictures", js("viewer.info.external") is True)

# second launch with another file -> handed to this window, no new process window
other_dir = tmp / "Other"
shutil.copytree(Path(args.samples) / "Screenshots", other_dir)
other = external.list_folder(str(other_dir))[0]
proc = subprocess.run([sys.executable, str(here / "main.py"), other],
                      env=dict(os.environ, QT_QPA_PLATFORM="offscreen"), timeout=30,
                      capture_output=True)
check("second launch exits after handing over", proc.returncode == 0)
check("running window switches to the new picture", wait(lambda: js("viewer.info.path") == other))
check("navigation now follows the new folder",
      wait(lambda: gallery.externalPhotos.itemCount == len(external.list_folder(str(other_dir)))))
pump(500)
root.grabWindow().save(str(out / "o2-handed-over.png"))

js("viewer.close()")
check("closing the viewer quits when started from the file manager", wait(lambda: bool(quit_requested), 5))

print("JS errors:", errors or "none")
print("FAILURES:", failures or "none")
gallery.shutdown()
shutil.rmtree(tmp, ignore_errors=True)
sys.exit(1 if failures or errors else 0)
