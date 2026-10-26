"""KDE share menu (the "Share" submenu of Dolphin / Gwenview), via the Purpose framework.

Purpose is a KDE library with a QML module (org.kde.purpose). It must be loaded by
the *system* Qt, not by the Qt bundled with pip's PySide6, so it runs in a small
helper (qml/share/ShareHelper.qml) under the system `qml` runtime:

    list mode:  prints the share targets for the files as JSON and exits
    run mode:   runs one target; shows a window only if it needs input
                (pick a KDE Connect device, an e-mail account, ...)

Protocol: the helper writes lines "LGSHARE <json>" to stderr (console.log).
"""

import glob
import json
import logging
import os
import shutil
import subprocess
from pathlib import Path

from PySide6.QtCore import QMimeDatabase, QUrl

log = logging.getLogger(__name__)

HELPER = Path(__file__).resolve().parent.parent / "qml" / "share" / "ShareHelper.qml"
MARKER = "LGSHARE "
QML_DIRS = ["/usr/lib/qt6/qml", "/usr/lib64/qt6/qml", "/usr/lib/x86_64-linux-gnu/qt6/qml",
            "/usr/lib/aarch64-linux-gnu/qt6/qml"]
# The clipboard target is handled in-process: a helper that exits would take the
# clipboard contents with it on desktops without a clipboard manager.
CLIPBOARD_IDS = ("clipboardplugin", "clipboard")


def qml_runtime() -> str | None:
    override = os.environ.get("ONEGALLERY_QML")
    if override:
        return override if os.access(override, os.X_OK) else None
    for candidate in ("/usr/lib/qt6/bin/qml", "/usr/lib64/qt6/bin/qml", shutil.which("qml6"),
                      shutil.which("qml")):
        if candidate and os.access(candidate, os.X_OK):
            return candidate
    return None


def purpose_installed() -> bool:
    extra = os.environ.get("ONEGALLERY_QML_IMPORT_PATH", "")
    dirs = [d for d in extra.split(os.pathsep) if d] + QML_DIRS
    return any(glob.glob(os.path.join(d, "org", "kde", "purpose", "qmldir")) for d in dirs)


def available() -> bool:
    return qml_runtime() is not None and purpose_installed()


def common_mime(paths: list[str]) -> str:
    db = QMimeDatabase()
    mimes = {db.mimeTypeForFile(p).name() for p in paths}
    if len(mimes) == 1:
        return mimes.pop()
    tops = {m.split("/")[0] for m in mimes}
    return f"{tops.pop()}/*" if len(tops) == 1 else "application/octet-stream"


def helper_env() -> dict:
    env = dict(os.environ)
    # never leak the pip-wheel Qt's paths into the system Qt helper
    for var in ("QML_IMPORT_PATH", "QML2_IMPORT_PATH", "QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH"):
        env.pop(var, None)
    extra = env.pop("ONEGALLERY_QML_IMPORT_PATH", "")
    if extra:
        env["QML_IMPORT_PATH"] = extra
    return env


def helper_command(mode: str, mime: str, plugin_id: str, paths: list[str]) -> list[str]:
    urls = [QUrl.fromLocalFile(p).toString() for p in paths]
    return [qml_runtime() or "qml", str(HELPER), "--", mode, mime, plugin_id or "-", *urls]


def parse_events(text: str) -> list[dict]:
    events = []
    for line in text.splitlines():
        pos = line.find(MARKER)
        if pos < 0:
            continue
        try:
            events.append(json.loads(line[pos + len(MARKER):]))
        except ValueError:
            log.debug("bad helper line: %s", line)
    return events


def list_targets(paths: list[str], mime: str) -> list[dict]:
    """Share targets for these files: [{"id", "name", "icon"}]. Runs in a worker."""
    if not available():
        return []
    cmd = helper_command("list", mime, "-", paths[:20])
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=20, env=helper_env())
    except (OSError, subprocess.TimeoutExpired) as exc:
        log.warning("share helper failed: %s", exc)
        return []
    for event in parse_events(result.stderr + result.stdout):
        if event.get("event") == "targets":
            return [t for t in event.get("targets", []) if t.get("id")]
    log.warning("share helper returned no targets (exit %s): %s", result.returncode,
                result.stderr.strip()[-500:])
    return []


def is_clipboard(plugin_id: str) -> bool:
    return plugin_id.lower() in CLIPBOARD_IDS or "clipboard" in plugin_id.lower()


def describe_result(event: dict) -> tuple[str, str]:
    """(toast message, url to copy) for a helper "finished" event."""
    error = int(event.get("error") or 0)
    output = event.get("output") or {}
    if error:
        message = event.get("message") or "Sharing failed"
        return (f"Sharing failed: {message}" if "fail" not in message.lower() else message), ""
    url = output.get("url") if isinstance(output, dict) else ""
    if url:
        return f"Link copied: {url}", url
    return "", ""
