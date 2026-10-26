#!/usr/bin/env python3
"""Check the application menu (global menu + ⋮ menu): every action works in context.

    python tools/menu_smoke.py samples --out /tmp/onegallery-menu-shots
"""
import argparse, os, sys, time, tempfile, shutil
from pathlib import Path
parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
parser.add_argument("samples")
parser.add_argument("--out", default="menu-shots")
args = parser.parse_args()
REPO = str(Path(__file__).resolve().parent.parent)
OUT = Path(args.out); OUT.mkdir(parents=True, exist_ok=True)
tmp = Path(tempfile.mkdtemp()); os.environ["ONEGALLERY_HOME"] = str(tmp / "home")
sys.path.insert(0, REPO)
from PySide6.QtCore import QCoreApplication, QEventLoop
from PySide6.QtQml import QQmlEngine, QQmlExpression
import main
from backend import editor as ed
lib = tmp / "lib"; shutil.copytree(Path(args.samples) / "Pets", lib / "Pets")
app, engine, g = main.create_app(["x"])
root = engine.rootObjects()[0]; root.setProperty("width", 1200); root.setProperty("height", 820)
fails = []
def js(c):
    e = QQmlExpression(QQmlEngine.contextForObject(root), root, c); v = e.evaluate()
    if e.hasError(): print("JS ERROR", c, e.error().toString()); fails.append(c)
    return v[0] if isinstance(v, tuple) else v
def pump(ms):
    end = time.time() + ms/1000
    while time.time() < end: QCoreApplication.processEvents(QEventLoop.AllEvents, 20); time.sleep(0.005)
def wait(p, t=20):
    end = time.time() + t
    while time.time() < end:
        pump(40)
        if p(): return True
    return False
def check(name, ok):
    print(("PASS " if ok else "FAIL ") + name)
    if not ok: fails.append(name)
# find a spec by path of texts
FIND = "(function(path){var list=appMenu.menus,spec=null;for(var i=0;i<path.length;++i){spec=null;for(var j=0;j<list.length;++j)if(list[j].text.replace('&','')===path[i])spec=list[j];if(!spec)return null;list=spec.items}return spec})"
def trig(*path):
    p = "[" + ",".join(repr(x) for x in path) + "]"
    if not js(f"{FIND}({p}) !== null"): print("missing spec", path); fails.append(path); return
    js(f"{FIND}({p}).triggered()")
def enabled(*path):
    p = "[" + ",".join(repr(x) for x in path) + "]"
    return js(f"{FIND}({p}).enabled")

g.addFolder(str(lib)); wait(lambda: not g.scanning and g.photos.itemCount > 0 and not g.photos.loading)
check("6 top-level menus", js("appMenu.menus.length") == 6)
check("popup menu built with 6 submenus", js("appPopup.count") == 6)
check("Edit Picture disabled without a picture", enabled("Edit", "Edit Picture…") is False)
trig("View", "Albums"); pump(400)
check("View > Albums switches tab", js("root.currentTab") == 2)
check("Albums checkmark follows", js(FIND+"(['View','Albums']).checked") is True)
trig("View", "Pictures"); pump(400)
first_desc = g.photos.itemAt(0)["path"]
trig("View", "Sort", "Oldest First"); wait(lambda: not g.photos.loading and g.photos.itemAt(0)["path"] != first_desc, 10)
check("Sort > Oldest First reorders", g.photos.itemAt(0)["path"] != first_desc and g.settings.sortAscending)
trig("View", "Sort", "Newest First"); wait(lambda: g.photos.itemAt(0)["path"] == first_desc, 10)
years = js("photos.years()")
check("Jump to Year lists years", len(years) >= 2)
js(f"{FIND}(['Go','Jump to Year']).picked({years[-1]})"); pump(600)
check("Jump to Year scrolls the grid", js("currentGrid.view.contentY") > 1000)
trig("Go", "Today"); pump(500)
check("Go > Today scrolls back to top", js("currentGrid.view.contentY - currentGrid.view.originY") < 50)
js(FIND+"(['View','Thumbnail Size']).picked(8)"); pump(300)
check("Thumbnail Size submenu sets columns", g.settings.columns == 8)
js("prefs.columns = 5")
# selection context
js("currentGrid.enterSelection(0); currentGrid.photoModel.toggleSelected(1)"); pump(200)
check("Copy Path enabled with a selection", enabled("Edit", "Copy Path") is True)
trig("Edit", "Deselect All"); pump(200)
check("Deselect All leaves selection mode", js("currentGrid.selectMode") is False)
# viewer context
js("Qt.callLater(function() { openViewer(currentGrid, 3) })"); pump(1200)  # deferred: see collections_smoke
path = js("viewer.info.path")
check("Edit Picture enabled in viewer", enabled("Edit", "Edit Picture…") is True)
trig("Go", "Next Picture"); pump(400)
check("Go > Next Picture", js("viewer.currentIndex") == 4)
trig("Go", "First Picture"); pump(400)
check("Go > First Picture", js("viewer.currentIndex") == 0)
js("viewer.goTo(3)"); pump(400)
w0 = js("viewer.info.width"); h0 = js("viewer.info.height")
trig("Edit", "Rotate", "Rotate Right")
check("Rotate Right saves with a backup", wait(lambda: ed.has_original(path) and js("viewer.info.width") == h0 and js("viewer.info.height") == w0, 20))
check("viewer still on the same picture", js("viewer.info.path") == path)
trig("Edit", "Add to Favorites"); pump(600)
check("Add to Favorites", js("viewer.info.favorite") is True)
check("menu text flips to Remove", js(FIND+"(['Edit','Remove from Favorites']) !== null"))
trig("View", "Show Details"); pump(400)
check("View > Show Details", js("viewer.detailsOpen") is True)
js("viewer.detailsOpen = false")
js(FIND+"(['Go','Albums']).picked(albums.entries[0])"); pump(900)
check("Go > Albums opens the album", js("stack.depth") == 2 and not js("viewer.visible"))
trig("Go", "Back"); pump(600)
check("Go > Back", js("stack.depth") == 1)
trig("Help", "Keyboard Shortcuts"); pump(500)
root.grabWindow().save(str(OUT) + "/m1-shortcuts.png")
check("Keyboard Shortcuts dialog", js("shortcutsDialog.opened") is True)
js("shortcutsDialog.close()"); pump(300)
trig("Help", "About One Gallery"); pump(500)
root.grabWindow().save(str(OUT) + "/m2-about.png")
js("aboutDialog.close()"); pump(300)
# open recent
other = sorted((lib / "Pets").iterdir())[0]
g.openFiles([str(other)]); wait(lambda: js("viewer.info.path") == str(other), 10)
check("Open Recent remembers files", js("prefs.recentFiles[0]") == str(other))
js("viewer.close()"); pump(700)
check("closing an opened file returns to the gallery (not standalone)", js("viewer.visible") is False)
# the in-app menu
js("openAppMenu(stack.currentItem.grid.view)"); pump(400)
js("appPopup.itemAt(2).subMenu.open()") ; pump(500)
root.grabWindow().save(str(OUT) + "/m3-popup-view.png")
js("appPopup.close()")
js("prefs.theme='dark'"); pump(300)
js("openAppMenu(stack.currentItem.grid.view)"); pump(300); js("appPopup.itemAt(1).subMenu.open()"); pump(500)
root.grabWindow().save(str(OUT) + "/m4-popup-edit-dark.png")
js("appPopup.close(); prefs.theme='system'")
print("FAILURES:", fails or "none")
g.shutdown(); shutil.rmtree(tmp, ignore_errors=True)
sys.exit(1 if fails else 0)
