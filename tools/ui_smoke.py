#!/usr/bin/env python3
"""Drive the real UI against a sample folder, save screenshots and measure scrolling.

    python tools/make_samples.py samples --count 5000
    python tools/ui_smoke.py samples --out /tmp/onegallery-shots

Uses a throw-away ONEGALLERY_HOME so your real index and settings are untouched.
"""

import argparse
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
parser.add_argument("samples")
parser.add_argument("--out", default="ui-shots")
parser.add_argument("--keep-home", action="store_true", help="reuse ./.smoke-home")
args = parser.parse_args()

home = Path(".smoke-home").resolve() if args.keep_home else Path(tempfile.mkdtemp(prefix="onegallery-smoke-"))
os.environ["ONEGALLERY_HOME"] = str(home)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QCoreApplication, QElapsedTimer, QEventLoop  # noqa: E402
from PySide6.QtQml import QQmlEngine, QQmlExpression  # noqa: E402

import main  # noqa: E402

app, engine, gallery = main.create_app([sys.argv[0]])
root = engine.rootObjects()[0]
out = Path(args.out)
out.mkdir(parents=True, exist_ok=True)
errors = []


def js(code):
    expr = QQmlExpression(QQmlEngine.contextForObject(root), root, code)
    value = expr.evaluate()
    if expr.hasError():
        errors.append(f"{code}: {expr.error().toString()}")
        print("JS ERROR", code, expr.error().toString())
    return value[0] if isinstance(value, tuple) else value


def pump(ms):
    end = time.time() + ms / 1000
    while time.time() < end:
        QCoreApplication.processEvents(QEventLoop.AllEvents, 20)
        time.sleep(0.005)


def wait(predicate, timeout=120):
    end = time.time() + timeout
    while time.time() < end:
        pump(50)
        if predicate():
            return True
    return False


def shot(name, settle=700):
    pump(settle)
    img = root.grabWindow()
    path = out / f"{name}.png"
    img.save(str(path))
    print("saved", path)


root.setProperty("width", 1200)
root.setProperty("height", 820)
shot("01-empty-state")

samples = str(Path(args.samples).resolve())
t0 = time.time()
gallery.addFolder(samples)
wait(lambda: gallery.scanning, 5)
wait(lambda: not gallery.scanning)
wait(lambda: gallery.photos.itemCount > 0 and not gallery.photos.loading, 30)
print(f"scan: {gallery.photos.itemCount} pictures indexed in {time.time() - t0:.1f}s")
shot("02-pictures", 2500)

# ---- scroll performance: animate contentY and record frame intervals
frames = []
timer = QElapsedTimer()
timer.start()
root.frameSwapped.connect(lambda: frames.append(timer.nsecsElapsed() / 1e6))
view_height = js("currentGrid.view.contentHeight")
print(f"grid content height: {view_height:.0f}px for {js('currentGrid.view.count')} rows")
start = time.time()
y = js("currentGrid.view.contentY")
step = 90
while time.time() - start < 4.0:
    y += step
    js(f"currentGrid.view.contentY = {y}")
    pump(8)
intervals = [b - a for a, b in zip(frames, frames[1:])]
if intervals:
    print(f"scroll: {len(frames)} frames in 4s, median frame {statistics.median(intervals):.1f}ms, "
          f"p95 {sorted(intervals)[int(len(intervals) * 0.95)]:.1f}ms, "
          f"max {max(intervals):.1f}ms")
shot("03-scrolled", 1500)

js("currentGrid.view.contentY = currentGrid.view.originY + 400")
shot("04-collapsed-header", 1200)
js("currentGrid.view.positionViewAtBeginning()")

js("prefs.columns = 8")
shot("05-eight-columns", 1500)
js("prefs.columns = 5")

js("currentGrid.enterSelection(0); currentGrid.photoModel.toggleSelected(2); currentGrid.photoModel.toggleSelected(3)")
shot("06-selection", 900)
js("currentGrid.exitSelection()")

js("Qt.callLater(function() { openViewer(currentGrid, 1) })"); pump(400)
shot("07-viewer", 1500)
js("viewer.detailsOpen = true")
shot("08-viewer-details", 900)
js("viewer.detailsOpen = false; viewer.close()")
pump(800)

js("stack.currentItem.current = 1")
shot("09-albums", 2000)
js("stack.currentItem.current = 3")
shot("10-folders", 1200)
js("stack.currentItem.current = 0")

js("openSearch()")
pump(600)
js("stack.currentItem.query = 'Screenshot'")
wait(lambda: not gallery.searchPhotos.loading and gallery.searchPhotos.itemCount > 0, 10)
shot("11-search", 1500)
js("goBack()")
pump(500)

js("openSettings()")
print("settings opens as the nav bar's gear tab:", js("root.currentTab") == js("root.settingsTab"))
shot("12-settings", 900)
js("goTab(0)")

js("prefs.theme = 'dark'")
shot("13-dark-pictures", 1200)
js("goTab(2)")
shot("14-dark-albums", 1500)
js("stack.currentItem.current = 0")
js("Qt.callLater(function() { openViewer(currentGrid, 0) })"); pump(400)
shot("15-dark-viewer", 1500)
js("viewer.close()")
pump(600)
js("prefs.theme = 'system'")

# incremental rescan should be fast and change nothing
finished = []
gallery.scanningChanged.connect(lambda: finished.append(not gallery.scanning))
t0 = time.time()
gallery.rescan()
wait(lambda: finished and finished[-1])
print(f"incremental rescan: {time.time() - t0:.2f}s")

print("JS errors:", errors or "none")
print("smoke home:", home)
gallery.shutdown()
