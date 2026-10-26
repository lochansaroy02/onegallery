#!/usr/bin/env python3
"""Render packaging/icon.svg into packaging/windows/onegallery.ico (16-256 px).

    python packaging/windows/make_icon.py
"""
import io
import sys
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

HERE = Path(__file__).resolve().parent
SVG = HERE.parent / "icon.svg"
OUT = HERE / "onegallery.ico"
SIZES = [16, 20, 24, 32, 40, 48, 64, 96, 128, 256]


def render(renderer: QSvgRenderer, size: int) -> Image.Image:
    img = QImage(size, size, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    painter = QPainter(img)
    painter.setRenderHint(QPainter.Antialiasing)
    renderer.render(painter)
    painter.end()
    data = QByteArray()
    buf = QBuffer(data)
    buf.open(QIODevice.WriteOnly)
    img.save(buf, "PNG")
    return Image.open(io.BytesIO(bytes(data))).convert("RGBA")


def main():
    app = QGuiApplication.instance() or QGuiApplication(sys.argv[:1])  # noqa: F841
    renderer = QSvgRenderer(str(SVG))
    if not renderer.isValid():
        sys.exit(f"cannot read {SVG}")
    images = [render(renderer, s) for s in SIZES]
    images[-1].save(OUT, format="ICO", sizes=[(s, s) for s in SIZES], append_images=images[:-1])
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
