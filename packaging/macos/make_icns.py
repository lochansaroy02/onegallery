#!/usr/bin/env python3
"""Render packaging/icon.svg into packaging/macos/onegallery.icns (needs macOS's iconutil).

    python packaging/macos/make_icns.py

The icon sits on Apple's grid: an 824 px shape centred on a 1024 px canvas with a soft
shadow below, so it lines up with other apps in the Dock and Finder.
"""
import io
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageFilter
from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRectF, Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

HERE = Path(__file__).resolve().parent
SVG = HERE.parent / "icon.svg"
OUT = HERE / "onegallery.icns"
CANVAS = 1024
SHAPE = 824          # the rounded square, per Apple's macOS icon grid
SVG_BOX = 240 / 256  # how much of icon.svg the rounded square fills


def render_master(renderer: QSvgRenderer) -> Image.Image:
    edge = SHAPE / SVG_BOX
    img = QImage(CANVAS, CANVAS, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    painter = QPainter(img)
    painter.setRenderHint(QPainter.Antialiasing)
    renderer.render(painter, QRectF((CANVAS - edge) / 2, (CANVAS - edge) / 2 - 10, edge, edge))
    painter.end()
    data = QByteArray()
    buf = QBuffer(data)
    buf.open(QIODevice.WriteOnly)
    img.save(buf, "PNG")
    art = Image.open(io.BytesIO(bytes(data))).convert("RGBA")
    # soft drop shadow, like Apple's own icons
    alpha = art.getchannel("A").point(lambda a: int(a * 0.32))
    shadow = Image.new("RGBA", art.size, (0, 0, 0, 0))
    shadow.putalpha(alpha)
    shadow = shadow.transform(art.size, Image.AFFINE, (1, 0, 0, 0, 1, -14)).filter(ImageFilter.GaussianBlur(18))
    return Image.alpha_composite(shadow, art)


def main():
    if not shutil.which("iconutil"):
        sys.exit("iconutil not found (it comes with macOS)")
    app = QGuiApplication.instance() or QGuiApplication(sys.argv[:1])  # noqa: F841
    renderer = QSvgRenderer(str(SVG))
    if not renderer.isValid():
        sys.exit(f"cannot read {SVG}")
    master = render_master(renderer)
    with tempfile.TemporaryDirectory() as tmp:
        iconset = Path(tmp) / "onegallery.iconset"
        iconset.mkdir()
        for size in (16, 32, 128, 256, 512):
            for scale in (1, 2):
                px = size * scale
                name = f"icon_{size}x{size}{'@2x' if scale == 2 else ''}.png"
                master.resize((px, px), Image.LANCZOS).save(iconset / name)
        subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(OUT)], check=True)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
