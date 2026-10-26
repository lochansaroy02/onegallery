# PyInstaller spec for the Windows build of One Gallery (used by packaging/windows/build.ps1).
#
#   pyinstaller packaging/windows/onegallery.spec --noconfirm --distpath dist --workpath build/pyinstaller
#
# Produces dist/OneGallery/OneGallery.exe plus its _internal folder (Python, Qt, QML, ffmpeg).
# Inno Setup (onegallery.iss) then packs that folder into the installer.
import os
import re
from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent.parent          # noqa: F821 (SPECPATH: set by PyInstaller)
WIN = ROOT / "packaging" / "windows"
VERSION = re.search(r'__version__ = "([^"]+)"', (ROOT / "backend" / "__init__.py").read_text()).group(1)
FFMPEG_DIR = Path(os.environ.get("ONEGALLERY_FFMPEG_DIR", ROOT / "build" / "ffmpeg"))

datas = [
    (str(ROOT / "qml"), "qml"),
    (str(ROOT / "packaging" / "icon.svg"), "packaging"),
    (str(ROOT / "LICENSE"), "."),
]
binaries = []
for tool in ("ffmpeg.exe", "ffprobe.exe"):   # bundled tools: found by backend._find_tool
    if (FFMPEG_DIR / tool).is_file():
        binaries.append((str(FFMPEG_DIR / tool), "ffmpeg"))
if (FFMPEG_DIR / "LICENSE.txt").is_file():
    datas.append((str(FFMPEG_DIR / "LICENSE.txt"), "ffmpeg"))

# Qt modules the QML uses only at run time (no Python import to discover them)
hiddenimports = [
    "PySide6.QtQuick", "PySide6.QtQuickControls2", "PySide6.QtMultimedia", "PySide6.QtPrintSupport",
    "PySide6.QtSvg", "PySide6.QtNetwork", "PySide6.QtQml",
    "backend.faces", "backend.video", "backend.desktop", "backend.printing", "backend.private",
    "cryptography.hazmat.primitives.ciphers.aead",
    "send2trash", "watchdog.observers", "pillow_heif",
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
    return any(f"Controls/{style}" in d for style in ("Material", "Universal", "Imagine"))


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

# Windows "Properties > Details" information
version_file = Path(workpath) / "version_info.txt"   # noqa: F821
parts = (VERSION.split(".") + ["0", "0", "0"])[:4]
nums = ", ".join(str(int(re.sub(r"\D.*", "", p) or 0)) for p in parts)
version_file.parent.mkdir(parents=True, exist_ok=True)
version_file.write_text(f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers=({nums}), prodvers=({nums})),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', 'One Gallery'),
      StringStruct('FileDescription', 'One Gallery photo and video gallery'),
      StringStruct('FileVersion', '{VERSION}'),
      StringStruct('InternalName', 'OneGallery'),
      StringStruct('LegalCopyright', 'MIT License'),
      StringStruct('OriginalFilename', 'OneGallery.exe'),
      StringStruct('ProductName', 'One Gallery'),
      StringStruct('ProductVersion', '{VERSION}')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
""", encoding="utf-8")

pyz = PYZ(a.pure)  # noqa: F821
exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="OneGallery",
    icon=str(WIN / "onegallery.ico"),
    version=str(version_file),
    console=False,
    upx=False,
)
coll = COLLECT(  # noqa: F821
    exe,
    a.binaries,
    a.datas,
    name="OneGallery",
    upx=False,
)
