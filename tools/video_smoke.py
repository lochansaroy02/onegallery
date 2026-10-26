#!/usr/bin/env python3
"""Drive the video features: indexing next to photos, the Videos tab, the muted inline
preview in the viewer and the built-in player. Needs ffmpeg to generate the test clips.

    QT_QPA_PLATFORM=offscreen python tools/video_smoke.py --out /tmp/onegallery-video-shots
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
parser.add_argument("--out", default="video-shots")
args = parser.parse_args()

if not shutil.which("ffmpeg"):
    sys.exit("ffmpeg is needed to generate test videos")

tmp = Path(tempfile.mkdtemp(prefix="onegallery-video-"))
os.environ["ONEGALLERY_HOME"] = str(tmp / "home")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image  # noqa: E402
from PySide6.QtCore import QCoreApplication, QEventLoop, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtQml import QQmlEngine, QQmlExpression  # noqa: E402

import main  # noqa: E402

OUT = Path(args.out)
OUT.mkdir(parents=True, exist_ok=True)
lib = tmp / "library"
lib.mkdir()
now = datetime.now().replace(microsecond=0)


def photo(name, when, color):
    exif = Image.Exif()
    exif.get_ifd(0x8769)[36867] = when.strftime("%Y:%m:%d %H:%M:%S")
    im = Image.effect_noise((800, 600), 40).convert("RGB")
    Image.blend(im, Image.new("RGB", im.size, color), 0.7).save(lib / name, exif=exif, quality=90)


def clip(name, when, seconds, size="640x360", src="testsrc2", extra=()):
    utc = when.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"{src}=size={size}:rate=25",
                    "-f", "lavfi", "-i", "sine=frequency=440", "-t", str(seconds), *extra,
                    "-metadata", f"creation_time={utc}", str(lib / name)], check=True)


# newest first: photo (now-1h), video (now-2h), photo (yesterday), video (2 days), mkv (3 days)
photo("a_new.jpg", now - timedelta(hours=1), (200, 120, 80))
clip("b_clip.mp4", now - timedelta(hours=2), 6, extra=("-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac"))
photo("c_yesterday.jpg", now - timedelta(days=1), (80, 160, 120))
clip("d_portrait.mov", now - timedelta(days=2), 4, size="360x640",
     extra=("-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac"))
clip("e_old.mkv", now - timedelta(days=3), 3, src="testsrc", extra=("-c:v", "libx264", "-pix_fmt", "yuv420p"))
expected = ["a_new.jpg", "b_clip.mp4", "c_yesterday.jpg", "d_portrait.mov", "e_old.mkv"]

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


def shot(name, settle=800):
    pump(settle)
    root.grabWindow().save(str(OUT / f"{name}.png"))


gallery.addFolder(str(lib))
wait(lambda: not gallery.scanning and gallery.photos.itemCount == 5 and not gallery.photos.loading)
order = [gallery.photos.itemAt(i)["name"] for i in range(gallery.photos.itemCount)]
print("   order:", order)
check("photos and videos in one chronological list", order == expected)
check("video count in the model", gallery.photos.videoCount == 3)
mov = gallery.photos.itemAt(3)
check("portrait video size / length", (mov["width"], mov["height"]) == (360, 640) and mov["duration"] == "0:04")
check("videos tab model", wait(lambda: gallery.videos.itemCount == 3 and not gallery.videos.loading, 10))
check("subtitle counts both", js("currentGrid.subtitle") == "2 pictures  ·  3 videos")
shot("v1-pictures-mixed", 2500)

js("goTab(1)")
pump(500)
check("Videos tab is current", js("root.currentTab") == 1 and js("currentGrid.photoModel === videos") is True)
shot("v2-videos-tab", 2500)
check("video thumbnails cached", len(list((tmp / "home" / "cache" / "thumbs").rglob("*.jpg"))) >= 3)
js("goTab(2)")
pump(600)
check("Videos album", any(a["kind"] == "videos" and a["count"] == 3 for a in gallery.albums.property("entries")))
js("goTab(0)")
pump(400)

# open the mp4 from the Pictures grid: plays muted right away
js("Qt.callLater(function() { openViewer(currentGrid, 1) })")
check("inline preview playing", wait(lambda: js("viewer.preview !== null && viewer.preview.playing") is True, 15))
check("preview muted by default", js("viewer.preview.muted") is True and js("viewer.videoMuted") is True)
check("first frame shown", wait(lambda: js("viewer.preview.frameShown") is True, 10))
check("preview advances", wait(lambda: (js("viewer.preview.position") or 0) > 600, 10))
shot("v3-viewer-inline", 600)
js("viewer.toggleMute()")
check("unmute", js("viewer.preview.muted") is False)
js("viewer.toggleMute()")
check("mute again", js("viewer.preview.muted") is True)

# S / 📷 saves the frame on screen next to the video and adds it to the library
before = gallery.photos.itemCount
js("viewer.forceActiveFocus()")
QTest.keyClick(root, Qt.Key_S)
check("S captures a frame", wait(lambda: len(list(lib.glob("b_clip_frame_*.jpg"))) == 1, 15))
check("capture added to the library", wait(lambda: gallery.photos.itemCount == before + 1, 10))
check("preview keeps playing from the same moment after a capture",
      wait(lambda: js("viewer.preview !== null && viewer.preview.playing") is True, 10) and (js("viewer.preview.position") or 0) > 500)
check("capture button next to mute", js("viewer.captureButton.enabled && viewer.captureButton.visible") is True)
shot("v3b-viewer-capture-button", 300)

# Play video -> built-in player with sound, continuing from the preview
js("Qt.callLater(function() { viewer.playCurrent() })")
check("player open", wait(lambda: js("playingVideo") is True, 5))
check("player playing with sound", wait(lambda: js("videoPlayer.playing") is True, 10) and js("videoPlayer.muted") is False)
check("inline preview stopped while the player is open", js("viewer.preview === null") is True)
pump(800)
p1 = js("videoPlayer.position")
js("videoPlayer.skip(2000)")
check("skip forward", wait(lambda: js("videoPlayer.position") >= p1 + 1500, 5))
shot("v4a-player-playing", 300)
js("videoPlayer.stepRate(1)")
check("speed 1.25×", js("videoPlayer.rate") == 1.25 and js("videoPlayer.video.playbackRate") == 1.25)
js("videoPlayer.togglePlay()")
pump(300)
check("pause", js("videoPlayer.playing") is False)
js("videoPlayer.poke()")
shot("v4-player-paused", 700)
js("videoPlayer.togglePlay()")
check("resume", wait(lambda: js("videoPlayer.playing") is True, 5))
js("videoPlayer.seekFraction(0.5)")
check("seek to 50 %", wait(lambda: abs(js("videoPlayer.position") - 3000) < 900, 5))
js("videoPlayer.captureFrame()")
check("player captures a frame too", wait(lambda: len(list(lib.glob("b_clip_frame_*.jpg"))) == 2, 15))
js("goBack()")
check("Esc closes the player", wait(lambda: js("playingVideo") is False, 3))
check("preview resumes muted", wait(lambda: js("viewer.preview !== null && viewer.preview.playing") is True, 10)
      and js("viewer.preview.muted") is True)

js("viewer.go(1)")
pump(600)
check("photo after video: no preview", js("viewer.isVideo") is False and js("viewer.preview === null") is True)
js("viewer.go(1)")
check("next video previews", wait(lambda: js("viewer.preview !== null && viewer.preview.playing") is True, 15))
shot("v5-viewer-portrait", 1200)
check("edit disabled for videos", js("appMenu.menus[1].items.filter(i => i.text === 'Edit Picture…')[0].enabled") is False)
js("goBack()")
check("Esc closes the viewer", wait(lambda: js("viewer.visible") is False, 3))

js("prefs.theme = 'dark'; goTab(1)")
shot("v6-videos-dark", 1500)
js("prefs.theme = 'system'")
print("FAILURES:", fails or "none")
gallery.shutdown()
shutil.rmtree(tmp, ignore_errors=True)
sys.exit(1 if fails else 0)
