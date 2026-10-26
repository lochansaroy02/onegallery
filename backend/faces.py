"""People: on-device face detection, recognition and grouping (optional feature).

Models (downloaded once, ~38 MB, Apache-2.0, from the OpenCV model zoo):
  * YuNet  - face detection
  * SFace  - 128-d face embeddings
Nothing leaves the computer: pictures are analysed locally and only the embeddings
and face boxes are stored in the index (tables `faces` and `persons`).

Grouping: a face joins an existing person when it is close enough to that person's
average face; leftover faces are clustered with a simple leader algorithm and become a
new person once at least MIN_FACES of them agree. Named/merged people stay stable.
"""

import hashlib
import logging
import os
import urllib.request

from PIL import Image, ImageOps
from PySide6.QtCore import QThread, Signal

from . import CACHE_DIR, DATA_DIR, db

log = logging.getLogger(__name__)
os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")

MODELS_DIR = DATA_DIR / "models"
FACE_CACHE = CACHE_DIR / "faces"
MODELS = {
    "detector": ("face_detection_yunet_2023mar.onnx",
                 "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/"
                 "face_detection_yunet_2023mar.onnx",
                 "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4"),
    "recognizer": ("face_recognition_sface_2021dec.onnx",
                   "https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/"
                   "face_recognition_sface_2021dec.onnx",
                   "0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79"),
}
FACES_VER = 1          # bump to re-detect every picture
ANALYSE_SIDE = 1280    # pictures are scaled to this long side for detection
MIN_SCORE = 0.85
ASSIGN_SIM = 0.42      # cosine similarity to join an existing person
LINK_SIM = 0.45        # ...to join a cluster of not-yet-grouped faces
MIN_FACES = 3          # pictures needed before a cluster becomes a person


def engine_available() -> bool:
    try:
        import cv2
        import numpy  # noqa: F401
    except ImportError:
        return False
    return hasattr(cv2, "FaceDetectorYN") and hasattr(cv2, "FaceRecognizerSF")


def model_path(key: str):
    return MODELS_DIR / MODELS[key][0]


def models_ready() -> bool:
    return all(model_path(k).exists() for k in MODELS)


def download_models(progress=None) -> None:
    """Download and verify the models. progress(done_bytes, total_bytes)."""
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    total = 38_928_942
    done = 0
    for key, (name, url, sha) in MODELS.items():
        dest = model_path(key)
        if dest.exists():
            done += dest.stat().st_size
            continue
        digest = hashlib.sha256()
        tmp = dest.with_suffix(".part")
        req = urllib.request.Request(url, headers={"User-Agent": "OneGallery"})
        with urllib.request.urlopen(req, timeout=60) as resp, open(tmp, "wb") as out:
            while True:
                chunk = resp.read(256 * 1024)
                if not chunk:
                    break
                out.write(chunk)
                digest.update(chunk)
                done += len(chunk)
                if progress:
                    progress(done, total)
        if digest.hexdigest() != sha:
            tmp.unlink(missing_ok=True)
            raise RuntimeError(f"Downloaded {name} is corrupted (checksum mismatch)")
        os.replace(tmp, dest)


def delete_face_data() -> None:
    conn = db.connect()
    with conn:
        conn.execute("DELETE FROM faces")
        conn.execute("DELETE FROM persons")
        conn.execute("UPDATE images SET faces_ver = 0")
    import shutil
    shutil.rmtree(FACE_CACHE, ignore_errors=True)


# ---- analysis --------------------------------------------------------------------------------
class FaceEngine:
    """Detector + recogniser. Not thread-safe: create one per thread."""

    def __init__(self):
        os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")
        import cv2
        import numpy as np
        self.cv2, self.np = cv2, np
        cv2.setNumThreads(2)  # leave CPU for the UI
        self.detector = cv2.FaceDetectorYN.create(str(model_path("detector")), "", (320, 320),
                                                  MIN_SCORE, 0.3, 5000)
        self.recognizer = cv2.FaceRecognizerSF.create(str(model_path("recognizer")), "")

    def analyse(self, path: str) -> list[tuple]:
        """[(x, y, w, h normalised, score, embedding float32[128])] for the faces in path."""
        np = self.np
        with Image.open(path) as im:
            im.draft("RGB", (ANALYSE_SIDE, ANALYSE_SIDE))
            im = ImageOps.exif_transpose(im).convert("RGB")
            im.thumbnail((ANALYSE_SIDE, ANALYSE_SIDE), Image.BILINEAR)
        bgr = np.ascontiguousarray(np.asarray(im)[:, :, ::-1])
        h, w = bgr.shape[:2]
        self.detector.setInputSize((w, h))
        _, found = self.detector.detect(bgr)
        if found is None:
            return []
        min_side = max(36, 0.025 * min(w, h))
        faces = []
        for row in found:
            fx, fy, fw, fh = (float(v) for v in row[:4])
            score = float(row[14])
            if score < MIN_SCORE or min(fw, fh) < min_side:
                continue
            aligned = self.recognizer.alignCrop(bgr, row)
            emb = self.recognizer.feature(aligned).astype(np.float32).ravel()
            norm = float(np.linalg.norm(emb))
            if norm == 0:
                continue
            faces.append((max(0.0, fx / w), max(0.0, fy / h), fw / w, fh / h, score, emb / norm))
        return faces


def store_faces(conn, image_id: int, faces: list[tuple]) -> None:
    conn.execute("DELETE FROM faces WHERE image_id = ?", (image_id,))
    conn.executemany(
        "INSERT INTO faces (image_id, x, y, w, h, score, embedding) VALUES (?, ?, ?, ?, ?, ?, ?)",
        [(image_id, x, y, w, h, s, e.tobytes()) for x, y, w, h, s, e in faces])
    conn.execute("UPDATE images SET faces_ver = ? WHERE id = ?", (FACES_VER, image_id))


# ---- grouping ---------------------------------------------------------------------------------
def cluster() -> dict:
    """Assign faces to people and create new people. Returns counts. Runs in a worker."""
    import numpy as np
    conn = db.connect()
    stats = {"assigned": 0, "new_people": 0}

    persons = conn.execute("SELECT id, centroid FROM persons WHERE centroid IS NOT NULL").fetchall()
    pending = conn.execute(
        "SELECT id, embedding, score FROM faces WHERE person_id IS NULL ORDER BY score DESC").fetchall()
    if pending:
        ids = np.array([r[0] for r in pending])
        emb = np.vstack([np.frombuffer(r[1], dtype=np.float32) for r in pending])
        left = np.ones(len(ids), dtype=bool)
        updates = []
        if persons:
            pids = np.array([p[0] for p in persons])
            cents = np.vstack([np.frombuffer(p[1], dtype=np.float32) for p in persons])
            for start in range(0, len(ids), 4096):
                sims = emb[start:start + 4096] @ cents.T
                best = sims.argmax(axis=1)
                ok = sims[np.arange(len(best)), best] >= ASSIGN_SIM
                for k in np.nonzero(ok)[0]:
                    updates.append((int(pids[best[k]]), int(ids[start + k])))
                    left[start + k] = False
        stats["assigned"] = len(updates)

        # leader clustering of the rest (highest-quality faces lead)
        rest = np.nonzero(left)[0]
        sums, members = [], []
        cents = np.zeros((0, emb.shape[1]), dtype=np.float32)
        for i in rest:
            e = emb[i]
            if len(members):
                sims = cents @ e
                j = int(sims.argmax())
                if sims[j] >= LINK_SIM:
                    members[j].append(i)
                    sums[j] = sums[j] + e
                    cents[j] = sums[j] / np.linalg.norm(sums[j])
                    continue
            members.append([i])
            sums.append(e.copy())
            cents = np.vstack([cents, e[None, :]])
        with conn:
            conn.executemany("UPDATE faces SET person_id = ? WHERE id = ?", updates)
            for group in members:
                images = {r[0] for r in conn.execute(
                    f"SELECT DISTINCT image_id FROM faces WHERE id IN ({','.join('?' * len(group))})",
                    [int(ids[i]) for i in group])}
                if len(images) < MIN_FACES:
                    continue
                pid = conn.execute("INSERT INTO persons (name) VALUES ('')").lastrowid
                conn.executemany("UPDATE faces SET person_id = ? WHERE id = ?",
                                 [(pid, int(ids[i])) for i in group])
                stats["new_people"] += 1
    refresh_people(conn)
    return stats


def refresh_people(conn=None) -> None:
    """Recompute centroid, cover face and picture count of every person."""
    import numpy as np
    conn = conn or db.connect()
    with conn:
        for (pid,) in conn.execute("SELECT id FROM persons").fetchall():
            rows = conn.execute(
                "SELECT f.id, f.embedding, f.score * f.w * f.h FROM faces f "
                "JOIN images i ON i.id = f.image_id WHERE f.person_id = ?", (pid,)).fetchall()
            if not rows:
                conn.execute("DELETE FROM persons WHERE id = ?", (pid,))
                continue
            mean = np.mean([np.frombuffer(r[1], dtype=np.float32) for r in rows], axis=0)
            mean = (mean / (np.linalg.norm(mean) or 1)).astype(np.float32)
            cover = max(rows, key=lambda r: r[2])[0]
            count = conn.execute(
                "SELECT COUNT(DISTINCT image_id) FROM faces WHERE person_id = ?", (pid,)).fetchone()[0]
            conn.execute("UPDATE persons SET centroid = ?, cover_face = ?, count = ? WHERE id = ?",
                         (mean.tobytes(), cover, count, pid))


def merge_people(source: int, target: int) -> None:
    conn = db.connect()
    with conn:
        name = conn.execute("SELECT name FROM persons WHERE id = ?", (target,)).fetchone()
        src_name = conn.execute("SELECT name FROM persons WHERE id = ?", (source,)).fetchone()
        conn.execute("UPDATE faces SET person_id = ? WHERE person_id = ?", (target, source))
        if name and not name[0] and src_name and src_name[0]:
            conn.execute("UPDATE persons SET name = ? WHERE id = ?", (src_name[0], target))
        conn.execute("DELETE FROM persons WHERE id = ?", (source,))
    refresh_people(conn)


def list_people(include_hidden=False) -> list[dict]:
    rows = db.connect().execute(
        "SELECT p.id, p.name, p.count, p.hidden, p.cover_face FROM persons p "
        + ("" if include_hidden else "WHERE p.hidden = 0 ")
        + "ORDER BY (p.name = ''), p.count DESC").fetchall()
    return [{"id": r[0], "name": r[1], "count": r[2], "hidden": bool(r[3]),
             "face": f"image://faces/{r[4]}/{r[2]}" if r[4] else ""} for r in rows]


# ---- face thumbnails (image://faces/<face id>/...) ----------------------------------------------
def face_thumbnail(face_id: int, size: int = 192) -> Image.Image:
    cached = FACE_CACHE / f"{face_id}.jpg"
    if cached.exists():
        with Image.open(cached) as im:
            return im.convert("RGB")
    row = db.connect().execute(
        "SELECT i.path, f.x, f.y, f.w, f.h FROM faces f JOIN images i ON i.id = f.image_id "
        "WHERE f.id = ?", (face_id,)).fetchone()
    if not row:
        raise FileNotFoundError(face_id)
    path, x, y, w, h = row
    with Image.open(path) as im:
        im.draft("RGB", (1600, 1600))
        im = ImageOps.exif_transpose(im).convert("RGB")
    W, H = im.size
    cx, cy = (x + w / 2) * W, (y + h / 2) * H
    side = max(w * W, h * H) * 1.7
    box = (int(cx - side / 2), int(cy - side / 2), int(cx + side / 2), int(cy + side / 2))
    face = im.crop(box).resize((size, size), Image.BICUBIC)
    try:
        FACE_CACHE.mkdir(parents=True, exist_ok=True)
        face.save(cached, "JPEG", quality=88)
    except OSError:
        pass
    return face


class FaceIndexThread(QThread):
    """Detects faces in every picture not analysed yet, then groups them into people."""

    progress = Signal(int, int)       # done, total
    indexFinished = Signal(dict)

    def run(self):
        stats = {"pictures": 0, "faces": 0, "errors": 0, "assigned": 0, "new_people": 0}
        try:
            engine = FaceEngine()
        except Exception as exc:
            log.error("face engine unavailable: %s", exc)
            stats["error"] = str(exc)
            self.indexFinished.emit(stats)
            return
        conn = db.connect()
        total = conn.execute(
            "SELECT COUNT(*) FROM images WHERE faces_ver < ? AND available = 1 AND video = 0",
            (FACES_VER,)).fetchone()[0]
        done = 0
        self.progress.emit(0, total)
        since_cluster = 0
        while not self.isInterruptionRequested():
            batch = conn.execute(
                "SELECT id, path FROM images WHERE faces_ver < ? AND available = 1 AND video = 0 "
                "ORDER BY taken DESC LIMIT 32", (FACES_VER,)).fetchall()
            if not batch:
                break
            for image_id, path in batch:
                if self.isInterruptionRequested():
                    break
                try:
                    faces = engine.analyse(path)
                except Exception as exc:  # unreadable / corrupt picture: mark as done
                    log.debug("faces: %s: %s", path, exc)
                    faces = []
                    stats["errors"] += 1
                with conn:
                    store_faces(conn, image_id, faces)
                stats["pictures"] += 1
                stats["faces"] += len(faces)
                since_cluster += len(faces)
                done += 1
                if done % 8 == 0:
                    self.progress.emit(done, max(total, done))
            if since_cluster >= 400:  # show people while a big library is still indexing
                part = cluster()
                stats["assigned"] += part["assigned"]
                stats["new_people"] += part["new_people"]
                since_cluster = 0
                self.progress.emit(done, max(total, done))
        part = cluster()
        stats["assigned"] += part["assigned"]
        stats["new_people"] += part["new_people"]
        stats["cancelled"] = self.isInterruptionRequested()
        self.indexFinished.emit(stats)
