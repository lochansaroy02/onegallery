#!/usr/bin/env python3
"""Drive the photo editor UI: tabs, filters, adjustments, crop, save as copy, save, revert.

    python tools/editor_smoke.py samples --out /tmp/onegallery-editor-shots

Works on a temporary copy of one sample sub-folder, with a throw-away ONEGALLERY_HOME.
"""

import argparse
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
parser.add_argument("samples")
parser.add_argument("--out", default="editor-shots")
args = parser.parse_args()

tmp = Path(tempfile.mkdtemp(prefix="onegallery-editor-"))
os.environ["ONEGALLERY_HOME"] = str(tmp / "home")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QCoreApplication, QEventLoop  # noqa: E402
from PySide6.QtQml import QQmlEngine, QQmlExpression  # noqa: E402

import main  # noqa: E402
from backend import editor as editor_mod  # noqa: E402

library = tmp / "library"
folders = [p for p in sorted(Path(args.samples).iterdir()) if p.is_dir() and not p.name.startswith(".")]
src = min(folders, key=lambda p: sum(1 for _ in p.iterdir()))  # smallest sample folder
shutil.copytree(src, library / src.name)

app, engine, gallery = main.create_app([sys.argv[0]])
root = engine.rootObjects()[0]
root.setProperty("width", 1200)
root.setProperty("height", 820)
out = Path(args.out)
out.mkdir(parents=True, exist_ok=True)
errors, failures = [], []


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


def wait(pred, timeout=30):
    end = time.time() + timeout
    while time.time() < end:
        pump(40)
        if pred():
            return True
    return False


def shot(name, settle=600):
    pump(settle)
    root.grabWindow().save(str(out / f"{name}.png"))


def check(name, ok):
    print(("PASS " if ok else "FAIL ") + name)
    if not ok:
        failures.append(name)


ed = engine.rootContext().contextProperty("editor")
gallery.addFolder(str(library))
wait(lambda: not gallery.scanning and gallery.photos.itemCount > 0 and not gallery.photos.loading)
count0 = gallery.photos.itemCount
print("pictures:", count0)

# ---- open the editor from the viewer
js("Qt.callLater(function() { openViewer(currentGrid, 0) })"); pump(400)
pump(800)
path0 = js("viewer.info.path")
js("openEditor(viewer.info)")
check("editor opens and renders a preview", wait(lambda: ed.property("previewUrl") != "", 10))
shot("e01-transform", 900)

js("editor.setAspect('1:1')")
shot("e02-crop-square", 700)
js("editor.rotateLeft()")
js("editor.setValue('straighten', 8); editor.commit()")
shot("e03-rotated-straightened", 800)

js("editorPage.tab = 'filters'")
check("filter thumbnails rendered", wait(lambda: js("editor.filterRevision") > 0, 10))
js("editor.setFilter('vintage')")
shot("e04-filters", 900)

js("editorPage.tab = 'adjust'; editorPage.adjustKey = 'exposure'")
js("editor.setValue('exposure', 0.4); editor.commit()")
js("editorPage.adjustKey = 'warmth'")
js("editor.setValue('warmth', -0.5); editor.commit()")
shot("e05-adjust", 900)

check("undo available", js("editor.canUndo") is True)
js("editor.undo()")
check("undo reverts last change", abs(js("editor.params.warmth")) < 1e-6)
js("editor.redo()")
check("redo re-applies", abs(js("editor.params.warmth") + 0.5) < 1e-6)

js("editorPage.comparing = true")
shot("e06-compare-original", 500)
js("editorPage.comparing = false")

# ---- save as copy
js("editorPage.saveCopy()")
check("save as copy finished", wait(lambda: not js("editorPage.visible"), 20))
check("copy appears in the grid", wait(lambda: gallery.photos.itemCount == count0 + 1, 10))
copy_path = editor_mod.copy_name(path0).replace("_edited_2", "_edited")
check("copy file written next to original", os.path.exists(copy_path))
pump(800)
check("viewer jumped to the copy", js("viewer.info.path") == copy_path)
shot("e07-viewer-after-copy", 900)
check("original untouched (no backup)", not editor_mod.has_original(path0))

# ---- save over the original, then revert
js("viewer.close()")
pump(600)
idx = gallery.photos.indexOfPath(path0)
js(f"Qt.callLater(function() {{ openViewer(currentGrid, {idx}) }})"); pump(400)
pump(800)
with open(path0, "rb") as f:
    original_bytes = f.read()
js("openEditor(viewer.info)")
wait(lambda: ed.property("previewUrl") != "", 10)
js("editor.setFilter('mono')")
js("editorPage.save()")
check("save finished", wait(lambda: not js("editorPage.visible"), 20))
check("backup of original kept", editor_mod.has_original(path0))
check("file changed on disk", open(path0, "rb").read() != original_bytes)
pump(1200)
check("viewer offers revert", js("viewer.canRevert") is True)
shot("e08-viewer-after-save", 900)

js("openEditor(viewer.info)")
wait(lambda: ed.property("previewUrl") != "", 10)
shot("e09-editor-with-revert", 900)
js("editor.revertOriginal(editor.path); editorPage.close()")
check("revert restores the original bytes",
      wait(lambda: open(path0, "rb").read() == original_bytes and not editor_mod.has_original(path0), 10))

# ---- discard confirmation
js("openEditor(viewer.info)")
wait(lambda: ed.property("previewUrl") != "", 10)
js("editor.rotateLeft()")
js("goBack()")
pump(400)
check("discard dialog shown for unsaved edits", js("confirmDialog.opened") is True)
shot("e10-discard-dialog", 500)
js("confirmDialog.close()")

js("prefs.theme = 'dark'; editorPage.close(); viewer.close()")
pump(600)
print("JS errors:", errors or "none")
print("FAILURES:", failures or "none")
gallery.shutdown()
shutil.rmtree(tmp, ignore_errors=True)
sys.exit(1 if failures or errors else 0)
