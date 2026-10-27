"""Feed for the Plasma "One Gallery Memories" widget (packaging/plasmoid).

The widget is plain QML running inside plasmashell, so it cannot open the index or decode
HEIC. One Gallery writes what it needs instead, into CACHE_DIR/widget:

    feed.json       {"version", "day", "generated", "lists": {"memories", "favorites", "recent"}}
    images/*.jpg    each picture, upright and at most IMAGE_EDGE px, named <path hash>_<version>

Every list item is {"image": <jpg in images/>, "path": <original file>, "title", "subtitle"}.
Pictures already rendered are reused, so a rebuild only decodes new ones. Images no list
refers to any more are deleted. The feed is rebuilt by the running app (WidgetFeed) and by
`onegallery --widget-feed`, which the widget runs when the feed is missing or from yesterday.
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

from . import CACHE_DIR, IS_LINUX, db, stories, thumbs
from .models import version
from .tasks import run_async

log = logging.getLogger(__name__)

PLUGIN_ID = "org.kde.onegallery.memories"
FEED_VERSION = 1
WIDGET_DIR = CACHE_DIR / "widget"
FEED_PATH = WIDGET_DIR / "feed.json"
IMAGE_DIR = WIDGET_DIR / "images"
IMAGE_EDGE = 1280      # long side of the rendered pictures
PER_LIST = 40          # pictures per list


def _config_home() -> Path:
    value = os.environ.get("XDG_CONFIG_HOME")
    return Path(value) if value else Path.home() / ".config"


def in_use() -> bool:
    """True when the widget sits on a Plasma desktop or panel (no point rendering otherwise)."""
    try:
        text = (_config_home() / "plasma-org.kde.plasma.desktop-appletsrc").read_text(
            encoding="utf-8", errors="replace")
    except OSError:
        return False
    return f"plugin={PLUGIN_ID}" in text


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


def _rows_to_items(rows, title: str) -> list[dict]:
    items = []
    for path, taken in rows:
        try:
            subtitle = _day_label(taken)
        except (OverflowError, OSError, ValueError):
            subtitle = ""
        items.append({"path": path, "title": title, "subtitle": subtitle})
    return items


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


def build_feed(today: date | None = None) -> dict:
    """Write feed.json and its images. Runs in a worker or the --widget-feed process."""
    today = today or date.today()
    with _locked():
        wanted = {"memories": _memories(), "favorites": _favorites(today), "recent": _recent()}
        rendered: dict[str, Path | None] = {}
        lists = {}
        for name, items in wanted.items():
            kept = []
            for item in items:
                if item["path"] not in rendered:
                    rendered[item["path"]] = _image_for(item["path"])
                image = rendered[item["path"]]
                if image is not None:
                    kept.append({"image": str(image), **item})
            lists[name] = kept

        used = {p.name for p in rendered.values() if p is not None}
        for f in IMAGE_DIR.iterdir() if IMAGE_DIR.exists() else ():
            if f.name not in used:
                try:
                    f.unlink()
                except OSError:
                    pass

        feed = {"version": FEED_VERSION, "day": today.isoformat(),
                "generated": datetime.now().isoformat(timespec="seconds"), "lists": lists}
        _write_json(FEED_PATH, feed)
    log.info("widget feed: %s", {k: len(v) for k, v in lists.items()})
    return feed


def run_cli() -> int:
    """`onegallery --widget-feed`: build the feed without opening a window."""
    logging.basicConfig(level=os.environ.get("ONEGALLERY_LOG", "WARNING").upper(),
                        format="%(levelname)s %(name)s: %(message)s")
    try:
        db.init()
        build_feed()
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

        run_async(build_feed, on_done=finished, on_error=finished)
