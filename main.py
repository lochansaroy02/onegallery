#!/usr/bin/env python3
"""One Gallery entry point: sets up Qt, the index, providers and models, then loads QML."""

import json
import logging
import os
import signal
import sys
from pathlib import Path

from PySide6.QtCore import QObject, QSize, Qt, QUrl
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtGui import QGuiApplication, QIcon, QPixmap
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickImageProvider
from PySide6.QtQuickControls2 import QQuickStyle

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

# "--self-test [report.txt]": start without a window or the user's data, check that the
# interface and the optional parts (video, printing, ffmpeg) load, then exit 0 / 1. Used by
# the Windows build to test the packaged OneGallery.exe. Set up before the backend is imported.
SELF_TEST = "--self-test" in sys.argv
if SELF_TEST:
    import tempfile
    os.environ["ONEGALLERY_HOME"] = tempfile.mkdtemp(prefix="onegallery-selftest-")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import backend  # noqa: E402
from backend import db, external  # noqa: E402
from backend.collections import Collections  # noqa: E402
from backend.controller import Gallery  # noqa: E402
from backend.editor import EditImageProvider, Editor  # noqa: E402
from backend.private import PrivateAlbum, PrivateImageProvider  # noqa: E402
from backend.settings import Settings  # noqa: E402
from backend.thumbs import ImageProvider  # noqa: E402

APP_ID = "onegallery"
SERVER_NAME = f"{APP_ID}-{os.getuid()}" if hasattr(os, "getuid") else APP_ID


def forward_to_running_instance(files: list[str]) -> bool:
    """If Gallery is already running, hand it the files (or just raise it) and return True."""
    sock = QLocalSocket()
    sock.connectToServer(SERVER_NAME)
    if not sock.waitForConnected(400):
        return False
    sock.write(json.dumps(files).encode() + b"\n")
    sock.flush()
    sock.waitForBytesWritten(1000)
    sock.disconnectFromServer()
    return True


class InstanceServer(QObject):
    """Receives files from later launches ("Open with Gallery" while Gallery is open)."""

    def __init__(self, gallery, parent=None):
        super().__init__(parent)
        self.gallery = gallery
        self.server = QLocalServer(self)
        self.server.newConnection.connect(self._accept)
        if not self.server.listen(SERVER_NAME):
            QLocalServer.removeServer(SERVER_NAME)  # stale socket from a crashed instance
            if not self.server.listen(SERVER_NAME):
                logging.getLogger(__name__).warning("single-instance server unavailable")

    def _accept(self):
        while self.server.hasPendingConnections():
            sock = self.server.nextPendingConnection()
            buffer = bytearray()

            def read(sock=sock, buffer=buffer):
                buffer.extend(bytes(sock.readAll()))
                if b"\n" in buffer:
                    try:
                        files = json.loads(buffer.split(b"\n", 1)[0].decode())
                    except ValueError:
                        files = []
                    sock.disconnectFromServer()
                    self.gallery.openFiles([str(f) for f in files])

            sock.readyRead.connect(read)
            sock.disconnected.connect(sock.deleteLater)


class ThemeIconProvider(QQuickImageProvider):
    """image://icon/<name> -> icon from the current (KDE) icon theme, for "Open with"."""

    def __init__(self):
        super().__init__(QQuickImageProvider.ImageType.Pixmap)

    def requestPixmap(self, icon_id, size, requested_size):
        edge = max(requested_size.width(), requested_size.height(), 48)
        icon = QIcon(icon_id) if os.path.isabs(icon_id) else QIcon.fromTheme(icon_id)
        pixmap = icon.pixmap(QSize(edge, edge)) if not icon.isNull() else QPixmap()
        if pixmap.isNull():  # unknown icon: a 1x1 transparent pixmap, QML shows its fallback
            pixmap = QPixmap(1, 1)
            pixmap.fill(Qt.transparent)
        if size is not None:
            size.setWidth(pixmap.width())
            size.setHeight(pixmap.height())
        return pixmap


def find_icon() -> str:
    for candidate in (HERE / "packaging" / "icon.svg",
                      Path("/usr/share/icons/hicolor/scalable/apps/onegallery.svg")):
        if candidate.exists():
            return str(candidate)
    return ""


def create_app(argv=None, files=None):
    """Build the application. Returns (app, engine, gallery).

    files: pictures to open right away in the viewer (opened from a file manager)."""
    logging.basicConfig(
        level=os.environ.get("ONEGALLERY_LOG", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    for line in backend.migrate_old_name():  # LGallery -> One Gallery, once
        logging.getLogger("onegallery").info(line)
    QGuiApplication.setApplicationName(APP_ID)
    QGuiApplication.setApplicationDisplayName("One Gallery")
    QGuiApplication.setOrganizationName(APP_ID)
    QGuiApplication.setDesktopFileName(APP_ID)  # Wayland: match onegallery.desktop for the icon
    if sys.platform == "win32":  # own taskbar group and icon instead of python.exe's
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("OneGallery.Gallery")
        except (AttributeError, OSError):
            pass
    # Basic is fully customisable; the KDE desktop style would override our One UI look.
    QQuickStyle.setStyle("Basic")

    app = QGuiApplication.instance() or QGuiApplication(argv or sys.argv)
    icon = find_icon()
    if icon:
        app.setWindowIcon(QIcon(icon))

    db.init()
    settings = Settings(app)
    gallery = Gallery(settings, app)
    collections = Collections(gallery, settings, app)
    editor = Editor(app)
    private_album = PrivateAlbum(gallery, settings, app)
    editor.libraryChanged.connect(gallery.reloadLibrary)
    editor.message.connect(gallery.toast)

    engine = QQmlApplicationEngine()
    engine.addImageProvider("thumbs", ImageProvider("thumbs"))
    engine.addImageProvider("full", ImageProvider("full", threads=2))
    engine.addImageProvider("faces", ImageProvider("faces", threads=2))
    engine.addImageProvider("icon", ThemeIconProvider())
    engine.addImageProvider("edit", EditImageProvider(editor))
    engine.addImageProvider("private", PrivateImageProvider(private_album.vault))

    ctx = engine.rootContext()
    ctx.setContextProperty("gallery", gallery)
    ctx.setContextProperty("prefs", settings)
    ctx.setContextProperty("photos", gallery.photos)
    ctx.setContextProperty("albumPhotos", gallery.albumPhotos)
    ctx.setContextProperty("searchPhotos", gallery.searchPhotos)
    ctx.setContextProperty("videos", gallery.videos)
    ctx.setContextProperty("albums", gallery.albums)
    ctx.setContextProperty("externalPhotos", gallery.externalPhotos)
    ctx.setContextProperty("launchedWithFiles", bool(files))
    ctx.setContextProperty("editor", editor)
    ctx.setContextProperty("collections", collections)
    ctx.setContextProperty("privateAlbum", private_album)
    ctx.setContextProperty("privatePhotos", private_album.photos)

    engine.load(QUrl.fromLocalFile(str(HERE / "qml" / "Main.qml")))
    if not engine.rootObjects():
        raise SystemExit("Failed to load the QML user interface (see errors above).")
    app.aboutToQuit.connect(gallery.shutdown)
    app.aboutToQuit.connect(collections.shutdown)
    app.aboutToQuit.connect(private_album.shutdown)
    if files:
        gallery.openFiles(files)
    return app, engine, gallery


def self_test() -> int:
    """See SELF_TEST above. Writes a report next to the argument after --self-test, if any."""
    from PySide6.QtCore import QTimer

    from backend import FFMPEG, FFPROBE, __version__, printing, vault

    args = sys.argv[1:]
    i = args.index("--self-test")
    report_path = args[i + 1] if i + 1 < len(args) and not args[i + 1].startswith("-") else ""
    lines, ok = [f"One Gallery {__version__} self-test", f"python {sys.version.split()[0]}"], True
    try:
        app, engine, gallery = create_app([sys.argv[0]])
        root = engine.rootObjects()[0]
        QTimer.singleShot(1500, app.quit)
        app.exec()
        player = root.property("videoPlayer")
        checks = {
            "interface (QML)": root is not None,
            "video playback (Qt Multimedia)": player is not None,
            "printing (Qt Print Support)": printing.AVAILABLE,
            "private album (cryptography)": vault.AVAILABLE,
            "ffmpeg": bool(FFMPEG and FFPROBE),
        }
        for name, passed in checks.items():
            lines.append(f"{'ok  ' if passed else 'FAIL'} {name}")
            ok &= bool(passed)
        gallery.shutdown()
    except BaseException as exc:  # report anything, including SystemExit from create_app
        lines.append(f"FAIL startup: {exc!r}")
        ok = False
    lines.append("PASSED" if ok else "FAILED")
    text = "\n".join(lines)
    print(text)
    if report_path:
        Path(report_path).write_text(text + "\n", encoding="utf-8")
    return 0 if ok else 1


def main():
    if SELF_TEST:
        sys.exit(self_test())
    args = sys.argv[1:]
    app = QGuiApplication.instance() or QGuiApplication(sys.argv)
    files = external.paths_from_args(args)
    if "--new-instance" not in args and forward_to_running_instance(files):
        return  # the running Gallery window shows the files
    app, engine, gallery = create_app(files=files)
    server = InstanceServer(gallery)  # noqa: F841 (kept alive for the app's lifetime)
    signal.signal(signal.SIGINT, signal.SIG_DFL)  # Ctrl+C in a terminal quits
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
