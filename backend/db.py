"""SQLite index: schema and per-thread connections."""

import sqlite3
import threading

from . import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS images (
    id        INTEGER PRIMARY KEY,
    path      TEXT NOT NULL UNIQUE,
    root      TEXT NOT NULL,          -- watched folder this file belongs to
    dir       TEXT NOT NULL,          -- parent directory
    name      TEXT NOT NULL,
    taken     INTEGER NOT NULL,       -- unix seconds (EXIF DateTimeOriginal or mtime)
    mtime     REAL NOT NULL,
    size      INTEGER NOT NULL,
    width     INTEGER NOT NULL DEFAULT 0,
    height    INTEGER NOT NULL DEFAULT 0,
    available INTEGER NOT NULL DEFAULT 1,
    favorite  INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_images_taken ON images(taken DESC);
CREATE INDEX IF NOT EXISTS idx_images_root ON images(root);
CREATE INDEX IF NOT EXISTS idx_images_dir ON images(dir);
CREATE INDEX IF NOT EXISTS idx_images_fav ON images(favorite) WHERE favorite = 1;

CREATE TABLE IF NOT EXISTS persons (
    id         INTEGER PRIMARY KEY,
    name       TEXT NOT NULL DEFAULT '',
    hidden     INTEGER NOT NULL DEFAULT 0,
    centroid   BLOB,                     -- mean face embedding (float32)
    cover_face INTEGER,
    count      INTEGER NOT NULL DEFAULT 0  -- pictures with this person
);
CREATE TABLE IF NOT EXISTS faces (
    id        INTEGER PRIMARY KEY,
    image_id  INTEGER NOT NULL REFERENCES images(id) ON DELETE CASCADE,
    x REAL, y REAL, w REAL, h REAL,      -- normalised box in the upright picture
    score     REAL NOT NULL,
    embedding BLOB NOT NULL,             -- 128 x float32, L2-normalised
    person_id INTEGER REFERENCES persons(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_faces_image ON faces(image_id);
CREATE INDEX IF NOT EXISTS idx_faces_person ON faces(person_id);

-- files already imported from a phone (or there when it was set up): never imported twice
CREATE TABLE IF NOT EXISTS phone_imports (
    device   TEXT NOT NULL,                  -- KDE Connect device id
    key      TEXT NOT NULL,                  -- path on the phone, below its storage
    size     INTEGER NOT NULL,
    mtime    INTEGER NOT NULL,
    imported INTEGER NOT NULL,               -- when (unix time)
    PRIMARY KEY (device, key)
);
"""

# columns added after the first release (migrated in place)
MIGRATIONS = [
    ("lat", "REAL"),
    ("lon", "REAL"),
    ("place", "TEXT"),                               # nearest town / city
    ("country", "TEXT"),
    ("meta_ver", "INTEGER NOT NULL DEFAULT 0"),     # which metadata (GPS...) has been read
    ("faces_ver", "INTEGER NOT NULL DEFAULT 0"),    # face detection done with this version
    ("video", "INTEGER NOT NULL DEFAULT 0"),        # 1 = video file
    ("duration", "REAL NOT NULL DEFAULT 0"),        # video length in seconds
]

_local = threading.local()


def connect() -> sqlite3.Connection:
    """Return this thread's connection, creating it on first use."""
    conn = getattr(_local, "conn", None)
    if conn is None or getattr(_local, "path", None) != DB_PATH:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(DB_PATH, timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("PRAGMA foreign_keys=ON")
        _local.conn = conn
        _local.path = DB_PATH
    return conn


def init() -> None:
    conn = connect()
    conn.executescript(SCHEMA)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(images)")}
    for name, decl in MIGRATIONS:
        if name not in columns:
            conn.execute(f"ALTER TABLE images ADD COLUMN {name} {decl}")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_images_place ON images(country, place)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_images_video ON images(taken DESC) WHERE video = 1")
    conn.commit()


def remove_root(root: str) -> int:
    conn = connect()
    with conn:
        cur = conn.execute("DELETE FROM images WHERE root = ?", (root,))
    return cur.rowcount


def set_favorite(ids: list[int], value: bool) -> None:
    conn = connect()
    with conn:
        conn.executemany(
            "UPDATE images SET favorite = ? WHERE id = ?", [(int(value), i) for i in ids]
        )


def delete_paths(paths: list[str]) -> None:
    conn = connect()
    with conn:
        conn.executemany("DELETE FROM images WHERE path = ?", [(p,) for p in paths])


def path_for_id(image_id: int) -> tuple[str, int] | None:
    row = connect().execute(
        "SELECT path, available FROM images WHERE id = ?", (image_id,)
    ).fetchone()
    return (row[0], row[1]) if row else None


def root_counts() -> dict[str, int]:
    rows = connect().execute("SELECT root, COUNT(*) FROM images GROUP BY root").fetchall()
    return dict(rows)
