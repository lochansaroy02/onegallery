"""Feed for the Plasma "One Gallery Memories" widget (packaging/plasmoid).

The widget is plain QML running inside plasmashell, so it cannot open the index or decode
HEIC. One Gallery writes what it needs instead, into CACHE_DIR/widget:

    feed.json       {"version", "day", "generated", "lists": {"memories", "favorites", "recent"},
                     "folders": {<folder>: [...]}}
    images/*.jpg    each picture, upright and at most IMAGE_EDGE px, named <path hash>_<version>

Every list item is {"image": <jpg in images/>, "path": <original file>, "title", "subtitle"}.
"folders" holds the folders widgets set to "Folders" show (any folder, in the library or not),
a different random selection of their pictures each day.

Pictures already rendered are reused, so a rebuild only decodes new ones. Images no list
refers to any more are deleted. The feed is rebuilt by the running app (WidgetFeed) and by
`onegallery --widget-feed [--folder DIR]...`, which the widget runs when the feed is missing,
from yesterday, or lacks one of its folders.
"""

import hashlib
import json
import logging
import os
import random
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path

from PySide6.QtCore import QDate, QLocale, QObject, QTimer, Slot

from . import CACHE_DIR, IS_LINUX, db, is_video, stories, supported_exts, thumbs
from .models import version
from .scanner import read_metadata, should_skip_dir
from .tasks import run_async

log = logging.getLogger(__name__)

PLUGIN_ID = "org.kde.onegallery.memories"
FEED_VERSION = 1
WIDGET_DIR = CACHE_DIR / "widget"
FEED_PATH = WIDGET_DIR / "feed.json"
IMAGE_DIR = WIDGET_DIR / "images"
IMAGE_EDGE = 1280      # long side of the rendered pictures
PER_LIST = 40          # pictures per list
PER_FOLDER = 60        # pictures per folder and day
FOLDER_SCAN_LIMIT = 50_000   # stop listing a huge folder tree after this many pictures


def _config_home() -> Path:
    value = os.environ.get("XDG_CONFIG_HOME")
    return Path(value) if value else Path.home() / ".config"


def _unescape_list(value: str) -> list[str]:
    r"""A KConfig string list: comma separated, with \, \\, \s ... escapes."""
    items, part, chars = [], [], iter(value)
    for ch in chars:
        if ch == "\\":
            nxt = next(chars, "")
            part.append({"s": " ", "t": "\t", "n": "\n", "r": "\r"}.get(nxt, nxt))
        elif ch == ",":
            items.append("".join(part))
            part = []
        else:
            part.append(ch)
    items.append("".join(part))
    return [item for item in items if item]


def _applets() -> list[dict]:
    """The General settings of every Memories widget on the Plasma desktop and panels."""
    try:
        text = (_config_home() / "plasma-org.kde.plasma.desktop-appletsrc").read_text(
            encoding="utf-8", errors="replace")
    except OSError:
        return []
    groups: dict[str, dict] = {}
    current = None
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("[") and line.endswith("]"):
            current = groups.setdefault(line, {})
        elif current is not None and "=" in line and not line.startswith("#"):
            key, value = line.split("=", 1)
            current[key.strip()] = value.strip()
    return [groups.get(name + "[Configuration][General]", {})
            for name, entries in groups.items() if entries.get("plugin") == PLUGIN_ID]


def in_use() -> bool:
    """True when the widget sits on a Plasma desktop or panel (no point rendering otherwise)."""
    return bool(_applets())


def configured_folders() -> list[str]:
    """Folders of the widgets set to show "Folders"."""
    folders = []
    for config in _applets():
        if config.get("source") == "folder":
            for folder in _unescape_list(config.get("folders", "")):
                if folder not in folders:
                    folders.append(folder)
    return folders


@contextmanager
def _locked():
    """One builder at a time: the app and `--widget-feed` may run together."""
    WIDGET_DIR.mkdir(parents=True, exist_ok=True)
    with open(WIDGET_DIR / ".lock", "w") as lock:
        try:
            import fcntl
            fcntl.flock(lock, fcntl.LOCK_EX)
        except (ImportError, OSError):  # no fcntl (Windows): the app is the only writer
            pass
        yield


def _day_label(taken: float) -> str:
    d = datetime.fromtimestamp(taken).date()
    return QLocale().toString(QDate(d.year, d.month, d.day), "dddd, MMMM d, yyyy")


def _memories() -> list[dict]:
    items = []
    for story in stories.memories():
        for item in story["items"]:
            items.append({"path": item["path"], "title": story["title"], "subtitle": item["date"]})
    return items[:PER_LIST]


def _item(path: str, taken, title: str) -> dict:
    try:
        subtitle = _day_label(taken) if taken is not None else ""
    except (OverflowError, OSError, ValueError):
        subtitle = ""
    return {"path": path, "title": title, "subtitle": subtitle}


def _rows_to_items(rows, title: str) -> list[dict]:
    return [_item(path, taken, title) for path, taken in rows]


def _favorites(today: date) -> list[dict]:
    """A different selection of favorites every day, shown newest first."""
    rows = db.connect().execute(
        "SELECT path, taken FROM images WHERE available = 1 AND video = 0 AND favorite = 1"
    ).fetchall()
    if len(rows) > PER_LIST:
        rows = random.Random(today.toordinal()).sample(rows, PER_LIST)
    rows.sort(key=lambda r: r[1], reverse=True)
    return _rows_to_items(rows, "Favorites")


def _recent() -> list[dict]:
    rows = db.connect().execute(
        "SELECT path, taken FROM images WHERE available = 1 AND video = 0 "
        "ORDER BY taken DESC LIMIT ?", (PER_LIST,)).fetchall()
    return _rows_to_items(rows, "Recent")


def _folder_pictures(folder: str) -> list[str]:
    """Every picture under folder (not videos), skipping the folders the scanner skips."""
    exts = supported_exts()
    found = []
    for dirpath, dirnames, filenames in os.walk(folder, onerror=lambda _e: None):
        dirnames[:] = sorted(d for d in dirnames if not should_skip_dir(d))
        for name in filenames:
            if os.path.splitext(name)[1].lower() in exts and not is_video(name):
                found.append(os.path.join(dirpath, name))
        if len(found) >= FOLDER_SCAN_LIMIT:
            break
    return found


def _folder(folder: str, today: date) -> list[dict]:
    """A different random selection of the folder's pictures every day."""
    paths = _folder_pictures(folder)
    rng = random.Random(f"{today.isoformat()} {folder}")
    if len(paths) > PER_FOLDER:
        paths = rng.sample(paths, PER_FOLDER)
    else:
        rng.shuffle(paths)
    known = {}
    if paths:
        marks = ",".join("?" * len(paths))
        known = dict(db.connect().execute(
            f"SELECT path, taken FROM images WHERE path IN ({marks})", paths).fetchall())
    title = os.path.basename(os.path.normpath(folder)) or folder
    items = []
    for path in paths:
        taken = known.get(path)
        if taken is None:   # not in the library: read the date from the file
            try:
                meta = read_metadata(path, os.stat(path).st_mtime)
            except OSError:
                meta = None
            taken = meta.taken if meta else None
        items.append(_item(path, taken, title))
    return items


def _image_for(path: str) -> Path | None:
    """The rendered copy of path, made now if needed; None if the file can't be read."""
    try:
        st = os.stat(path)
    except OSError:
        return None
    digest = hashlib.sha1(path.encode("utf-8", "surrogateescape")).hexdigest()[:20]
    out = IMAGE_DIR / f"{digest}_{version(st.st_mtime, st.st_size)}.jpg"
    if out.exists():
        return out
    try:
        im = thumbs.load_full(path, IMAGE_EDGE, IMAGE_EDGE)
        IMAGE_DIR.mkdir(parents=True, exist_ok=True)
        tmp = out.with_suffix(".tmp%d" % os.getpid())
        im.save(tmp, "JPEG", quality=85)
        os.replace(tmp, out)
    except Exception as exc:  # unreadable or corrupt picture: leave it out of the widget
        log.debug("widget: cannot render %s: %s", path, exc)
        return None
    return out


def _write_json(path: Path, data: dict) -> None:
    tmp = path.with_suffix(".tmp%d" % os.getpid())
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def build_feed(today: date | None = None, folders=()) -> dict:
    """Write feed.json and its images. Runs in a worker or the --widget-feed process."""
    today = today or date.today()
    with _locked():
        rendered: dict[str, Path | None] = {}

        def render(items):
            kept = []
            for item in items:
                if item["path"] not in rendered:
                    rendered[item["path"]] = _image_for(item["path"])
                image = rendered[item["path"]]
                if image is not None:
                    kept.append({"image": str(image), **item})
            return kept

        lists = {"memories": render(_memories()), "favorites": render(_favorites(today)),
                 "recent": render(_recent())}
        # every requested folder gets an entry, empty if it's missing, so the widget can tell
        # "no pictures there" from "not built yet"
        folder_lists = {folder: render(_folder(folder, today)) for folder in dict.fromkeys(folders)}

        used = {p.name for p in rendered.values() if p is not None}
        for f in IMAGE_DIR.iterdir() if IMAGE_DIR.exists() else ():
            if f.name not in used:
                try:
                    f.unlink()
                except OSError:
                    pass

        feed = {"version": FEED_VERSION, "day": today.isoformat(),
                "generated": datetime.now().isoformat(timespec="seconds"), "lists": lists,
                "folders": folder_lists}
        _write_json(FEED_PATH, feed)
    log.info("widget feed: %s, folders %s", {k: len(v) for k, v in lists.items()},
             {k: len(v) for k, v in folder_lists.items()})
    return feed


def run_cli(args: list[str]) -> int:
    """`onegallery --widget-feed [--folder DIR]...`: build the feed without opening a window.
    The widget passes its folders, which Plasma may not have saved to its config file yet."""
    logging.basicConfig(level=os.environ.get("ONEGALLERY_LOG", "WARNING").upper(),
                        format="%(levelname)s %(name)s: %(message)s")
    folders = [os.path.abspath(os.path.expanduser(args[i + 1]))
               for i, arg in enumerate(args[:-1]) if arg == "--folder"]
    try:
        db.init()
        build_feed(folders=folders + configured_folders())
    except Exception as exc:  # the widget only looks at the exit code
        log.error("could not build the widget feed: %s", exc)
        return 1
    print(FEED_PATH)
    return 0


class WidgetFeed(QObject):
    """Keeps the feed current while One Gallery runs (Linux, and only when the widget is used)."""

    def __init__(self, gallery, collections, parent=None):
        super().__init__(parent)
        self._busy = False
        self._again = False
        self._timer = QTimer(self, singleShot=True, interval=3000)
        self._timer.timeout.connect(self.rebuild)
        if not IS_LINUX:
            return
        collections.storiesChanged.connect(self._timer.start)  # library changed or a new day
        gallery.favoritesChanged.connect(self._timer.start)
        self._timer.start()

    @Slot()
    def rebuild(self):
        if not in_use():
            return
        if self._busy:
            self._again = True
            return
        self._busy = True

        def finished(_result=None):
            self._busy = False
            if self._again:
                self._again = False
                self._timer.start()

        run_async(lambda: build_feed(folders=configured_folders()),
                  on_done=finished, on_error=finished)
