# PyInstaller spec for the macOS build of One Gallery (used by packaging/macos/build.sh).
#
#   pyinstaller packaging/macos/onegallery.spec --noconfirm --distpath dist --workpath build/pyinstaller
#
# Produces "dist/One Gallery.app" for the Mac it is built on (Apple Silicon or Intel).
# build.sh then signs it ad hoc and packs it into a .dmg.
import os
import re
from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent.parent          # noqa: F821 (SPECPATH: set by PyInstaller)
MAC = ROOT / "packaging" / "macos"
VERSION = re.search(r'__version__ = "([^"]+)"', (ROOT / "backend" / "__init__.py").read_text()).group(1)
FFMPEG_DIR = Path(os.environ.get("ONEGALLERY_FFMPEG_DIR", ROOT / "build" / "ffmpeg-mac"))
BUNDLE_ID = "io.github.lochansaroy02.onegallery"

datas = [
    (str(ROOT / "qml"), "qml"),
    (str(ROOT / "packaging" / "icon.svg"), "packaging"),
    (str(ROOT / "LICENSE"), "."),
]
binaries = []
for tool in ("ffmpeg", "ffprobe"):   # bundled tools: found by backend._find_tool
    if (FFMPEG_DIR / tool).is_file():
        binaries.append((str(FFMPEG_DIR / tool), "ffmpeg"))
if (FFMPEG_DIR / "README.txt").is_file():
    datas.append((str(FFMPEG_DIR / "README.txt"), "ffmpeg"))

# Qt modules the QML uses only at run time (no Python import to discover them)
hiddenimports = [
    "PySide6.QtQuick", "PySide6.QtQuickControls2", "PySide6.QtMultimedia", "PySide6.QtPrintSupport",
    "PySide6.QtSvg", "PySide6.QtNetwork", "PySide6.QtQml",
    "backend.faces", "backend.video", "backend.desktop", "backend.printing", "backend.private",
    "backend.macos",
    "cryptography.hazmat.primitives.ciphers.aead",
    "watchdog.observers", "pillow_heif",
]
# big Qt parts One Gallery never uses
UNUSED = [
    "WebEngine", "WebView", "WebChannel", "WebSockets", "Pdf", "Quick3D", "Qt3D", "3DCore", "3DRender",
    "3DInput", "3DLogic", "3DExtras", "3DAnimation", "Charts", "DataVisualization", "Graphs",
    "Location", "Sensors", "Scxml", "StateMachine", "VirtualKeyboard", "TextToSpeech", "SpatialAudio",
    "RemoteObjects", "Designer", "Help", "Bluetooth", "Nfc", "SerialPort", "SerialBus", "HttpServer",
    "Positioning", "QuickTest", "Lottie",
]
excludes = ["tkinter", "pydoc"] + [
    f"PySide6.Qt{name}" for name in UNUSED if not name.startswith("3D")]


def unused(dest: str) -> bool:
    d = dest.replace("\\", "/")
    for name in UNUSED:
        if (f"Qt6{name}" in d or f"/Qt{name}/" in d or d.endswith(f"/Qt{name}") or f"qml/Qt{name}" in d
                or f"Qt{name}.framework" in d or d.startswith(f"Qt{name}")):
            return True
    # Quick Controls styles: One Gallery uses Basic (and Dialogs fall back to it)
    return any(f"Controls/{style}" in d for style in ("Material", "Universal", "Imagine", "iOS"))


a = Analysis(  # noqa: F821
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=excludes,
    noarchive=False,
)
a.binaries = [b for b in a.binaries if not unused(b[0])]
a.datas = [d for d in a.datas if not unused(d[0])]

pyz = PYZ(a.pure)  # noqa: F821
exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="OneGallery",
    console=False,
    upx=False,
    argv_emulation=False,   # main.py handles Finder's open-file events itself
)
coll = COLLECT(  # noqa: F821
    exe,
    a.binaries,
    a.datas,
    name="OneGallery",
    upx=False,
)

PICTURES = ["public.jpeg", "public.png", "org.webmproject.webp", "com.compuserve.gif",
            "com.microsoft.bmp", "public.tiff", "public.heic", "public.heif"]
VIDEOS = ["public.mpeg-4", "com.apple.quicktime-movie", "com.apple.m4v-video", "public.avi",
          "org.matroska.mkv", "org.webmproject.webm", "public.3gpp", "public.mpeg",
          "public.avchd-mpeg-2-transport-stream", "com.microsoft.windows-media-wmv"]

app = BUNDLE(  # noqa: F821
    coll,
    name="One Gallery.app",
    icon=str(MAC / "onegallery.icns"),
    bundle_identifier=BUNDLE_ID,
    version=VERSION,
    info_plist={
        "CFBundleName": "One Gallery",
        "CFBundleDisplayName": "One Gallery",
        "CFBundleShortVersionString": VERSION,
        "CFBundleVersion": VERSION,
        "LSMinimumSystemVersion": "13.0",
        "LSApplicationCategoryType": "public.app-category.photography",
        "NSHighResolutionCapable": True,
        "NSRequiresAquaSystemAppearance": False,   # follow light / dark mode
        "NSHumanReadableCopyright": "MIT License",
        # "Open With" in Finder, and Settings > Default app
        "CFBundleDocumentTypes": [
            {"CFBundleTypeName": "Picture", "CFBundleTypeRole": "Viewer",
             "LSHandlerRank": "Alternate", "LSItemContentTypes": PICTURES},
            {"CFBundleTypeName": "Video", "CFBundleTypeRole": "Viewer",
             "LSHandlerRank": "Alternate", "LSItemContentTypes": VIDEOS},
        ],
        # what macOS shows when it asks for permission
        "NSAppleEventsUsageDescription":
            "One Gallery asks System Events to change the desktop picture when you choose Set as › Wallpaper.",
        "NSDesktopFolderUsageDescription": "One Gallery shows the pictures in the folders you add.",
        "NSDocumentsFolderUsageDescription": "One Gallery shows the pictures in the folders you add.",
        "NSDownloadsFolderUsageDescription": "One Gallery shows the pictures in the folders you add.",
        "NSRemovableVolumesUsageDescription": "One Gallery shows the pictures on drives you add.",
        "NSNetworkVolumesUsageDescription": "One Gallery shows the pictures on network drives you add.",
    },
)
