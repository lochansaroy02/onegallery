"""macOS integration through LaunchServices, called with ctypes (no extra packages).

- apps_for_file / open_with: the "Open with" list, like Finder's.
- default_viewer_status / set_default_viewer: make One Gallery open pictures from Finder.
  This only works for the bundled app (One Gallery.app), whose Info.plist declares the
  picture types; run from source, the status is "not-installed".
"""

import ctypes
import logging
import os
import plistlib
import subprocess
import sys

log = logging.getLogger(__name__)

BUNDLE_ID = "io.github.lochansaroy02.onegallery"

# picture types One Gallery offers to open by default (MIME type -> Uniform Type Identifier)
MIME_TO_UTI = {
    "image/jpeg": "public.jpeg",
    "image/png": "public.png",
    "image/webp": "org.webmproject.webp",
    "image/gif": "com.compuserve.gif",
    "image/bmp": "com.microsoft.bmp",
    "image/tiff": "public.tiff",
    "image/heic": "public.heic",
    "image/heif": "public.heif",
}

_UTF8 = 0x08000100           # kCFStringEncodingUTF8
_ROLES_ALL = 0xFFFFFFFF      # kLSRolesAll
_ROLES_VIEWER = 0x00000002   # kLSRolesViewer

_cf = None
_ls = None


def _libs():
    global _cf, _ls
    if _cf is None:
        cf = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
        ls = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/CoreServices.framework/CoreServices")
        vp, cp, lng = ctypes.c_void_p, ctypes.c_char_p, ctypes.c_long
        cf.CFStringCreateWithCString.argtypes = [vp, cp, ctypes.c_uint32]
        cf.CFStringCreateWithCString.restype = vp
        cf.CFStringGetCString.argtypes = [vp, cp, lng, ctypes.c_uint32]
        cf.CFStringGetCString.restype = ctypes.c_bool
        cf.CFRelease.argtypes = [vp]
        cf.CFURLCreateFromFileSystemRepresentation.argtypes = [vp, cp, lng, ctypes.c_bool]
        cf.CFURLCreateFromFileSystemRepresentation.restype = vp
        cf.CFURLGetFileSystemRepresentation.argtypes = [vp, ctypes.c_bool, cp, lng]
        cf.CFURLGetFileSystemRepresentation.restype = ctypes.c_bool
        cf.CFArrayGetCount.argtypes = [vp]
        cf.CFArrayGetCount.restype = lng
        cf.CFArrayGetValueAtIndex.argtypes = [vp, lng]
        cf.CFArrayGetValueAtIndex.restype = vp
        cf.CFBundleGetMainBundle.restype = vp
        cf.CFBundleGetIdentifier.argtypes = [vp]
        cf.CFBundleGetIdentifier.restype = vp
        ls.LSCopyApplicationURLsForURL.argtypes = [vp, ctypes.c_uint32]
        ls.LSCopyApplicationURLsForURL.restype = vp
        ls.LSCopyDefaultRoleHandlerForContentType.argtypes = [vp, ctypes.c_uint32]
        ls.LSCopyDefaultRoleHandlerForContentType.restype = vp
        ls.LSSetDefaultRoleHandlerForContentType.argtypes = [vp, ctypes.c_uint32, vp]
        ls.LSSetDefaultRoleHandlerForContentType.restype = ctypes.c_int32
        _cf, _ls = cf, ls
    return _cf, _ls


def _cfstr(text: str):
    cf, _ = _libs()
    return cf.CFStringCreateWithCString(None, text.encode(), _UTF8)


def _pystr(ref) -> str:
    if not ref:
        return ""
    cf, _ = _libs()
    buf = ctypes.create_string_buffer(1024)
    return buf.value.decode() if cf.CFStringGetCString(ref, buf, len(buf), _UTF8) else ""


def _url_path(url) -> str:
    cf, _ = _libs()
    buf = ctypes.create_string_buffer(4096)
    return buf.value.decode() if cf.CFURLGetFileSystemRepresentation(url, True, buf, len(buf)) else ""


def own_bundle_id() -> str:
    """One Gallery's bundle identifier when it runs as One Gallery.app, else ""."""
    if sys.platform != "darwin" or not getattr(sys, "frozen", False):
        return ""
    cf, _ = _libs()
    bundle = cf.CFBundleGetMainBundle()
    ident = _pystr(cf.CFBundleGetIdentifier(bundle)) if bundle else ""
    return ident if ident.lower() == BUNDLE_ID else ""


def _app_info(app: str) -> tuple[str, str]:
    """(display name, path of its .icns icon or "")."""
    name, icon = os.path.splitext(os.path.basename(app))[0], ""
    try:
        with open(os.path.join(app, "Contents", "Info.plist"), "rb") as f:
            info = plistlib.load(f)
    except (OSError, plistlib.InvalidFileException, ValueError):
        return name, icon
    name = info.get("CFBundleDisplayName") or info.get("CFBundleName") or name
    icon_file = info.get("CFBundleIconFile") or ""
    if icon_file:
        if not icon_file.endswith(".icns"):
            icon_file += ".icns"
        candidate = os.path.join(app, "Contents", "Resources", icon_file)
        icon = candidate if os.path.isfile(candidate) else ""
    return name, icon


def apps_for_file(path: str) -> list[dict]:
    """Applications that can open path, as {id, name, icon, file} (file: the .app path)."""
    cf, ls = _libs()
    raw = os.fsencode(path)
    url = cf.CFURLCreateFromFileSystemRepresentation(None, raw, len(raw), False)
    if not url:
        return []
    apps, seen = [], set()
    try:
        array = ls.LSCopyApplicationURLsForURL(url, _ROLES_ALL)
        if not array:
            return []
        try:
            own = os.path.realpath(sys.executable).split(".app/")[0] + ".app" if getattr(sys, "frozen", False) else ""
            for i in range(cf.CFArrayGetCount(array)):
                app = _url_path(cf.CFArrayGetValueAtIndex(array, i)).rstrip("/")
                if not app or (own and os.path.realpath(app) == own):
                    continue
                name, icon = _app_info(app)
                if name.lower() in seen:  # the same app installed twice
                    continue
                seen.add(name.lower())
                apps.append({"id": app, "name": name, "icon": icon, "file": app})
        finally:
            cf.CFRelease(array)
    finally:
        cf.CFRelease(url)
    apps.sort(key=lambda a: a["name"].lower())
    return apps


def open_with(app: str, paths: list[str]) -> bool:
    try:
        subprocess.Popen(["open", "-a", app, *paths], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except OSError as exc:
        log.warning("could not open with %s: %s", app, exc)
        return False


def _handler(uti: str) -> str:
    cf, ls = _libs()
    ref = _cfstr(uti)
    try:
        handler = ls.LSCopyDefaultRoleHandlerForContentType(ref, _ROLES_VIEWER)
        try:
            return _pystr(handler)
        finally:
            if handler:
                cf.CFRelease(handler)
    finally:
        cf.CFRelease(ref)


def default_viewer_status(mimes: list[str]) -> str:
    """"default" | "partial" | "other" | "not-installed" (not running as One Gallery.app)."""
    own = own_bundle_id()
    if not own:
        return "not-installed"
    utis = [MIME_TO_UTI[m] for m in mimes if m in MIME_TO_UTI]
    ours = [u for u in utis if _handler(u).lower() == own.lower()]
    if len(ours) == len(utis):
        return "default"
    return "partial" if ours else "other"


def set_default_viewer(mimes: list[str]) -> None:
    own = own_bundle_id()
    if not own:
        raise RuntimeError("Open One Gallery from the Applications folder first")
    cf, ls = _libs()
    bundle = _cfstr(own)
    failed = []
    try:
        for uti in (MIME_TO_UTI[m] for m in mimes if m in MIME_TO_UTI):
            ref = _cfstr(uti)
            try:
                if ls.LSSetDefaultRoleHandlerForContentType(ref, _ROLES_ALL, bundle) != 0:
                    failed.append(uti)
            finally:
                cf.CFRelease(ref)
    finally:
        cf.CFRelease(bundle)
    if failed:
        raise RuntimeError("macOS didn't allow One Gallery for " + ", ".join(failed))
