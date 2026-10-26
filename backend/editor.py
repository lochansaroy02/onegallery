"""Photo editor: non-destructive edit parameters, preview rendering, save / save as copy / revert.

Edits are a small dict of parameters (geometry, light/colour adjustments, a filter
preset). The preview is rendered from a downscaled copy on a worker thread; saving
re-applies the same parameters to the full-resolution image. Before a file is
overwritten for the first time its untouched original is copied to
~/.local/share/onegallery/originals/ so "Revert to original" can restore it later.
"""

import copy
import hashlib
import logging
import math
import os
import shutil
from datetime import datetime

from PIL import Image, ImageEnhance, ImageFilter, ImageOps
from PySide6.QtCore import Property, QObject, Signal, Slot
from PySide6.QtGui import QImage
from PySide6.QtQuick import QQuickImageProvider

from . import DATA_DIR, db, is_video
from .models import format_size
from .scanner import UPSERT, read_metadata
from .tasks import run_async

log = logging.getLogger(__name__)

ORIGINALS_DIR = DATA_DIR / "originals"
PREVIEW_MAX = 1600
FILTER_THUMB = 160
FULL_CROP = [0.0, 0.0, 1.0, 1.0]

DEFAULTS = {
    "rotate": 0,            # degrees counter-clockwise, multiple of 90
    "flipH": False,
    "flipV": False,
    "straighten": 0.0,      # degrees, -45..45
    "crop": FULL_CROP,      # normalised x, y, w, h of the straightened image
    "aspect": "free",
    "brightness": 0.0, "exposure": 0.0, "contrast": 0.0, "highlights": 0.0,
    "shadows": 0.0, "saturation": 0.0, "warmth": 0.0, "tint": 0.0,
    "sharpness": 0.0, "vignette": 0.0,   # all -1..1
    "filter": "none",
    "filterStrength": 1.0,  # 0..1
}

ADJUSTMENTS = [
    ("brightness", "Brightness", "sun"),
    ("exposure", "Exposure", "exposure"),
    ("contrast", "Contrast", "contrast"),
    ("highlights", "Highlights", "highlights"),
    ("shadows", "Shadows", "shadows"),
    ("saturation", "Saturation", "drop"),
    ("warmth", "Warmth", "thermo"),
    ("tint", "Tint", "tint"),
    ("sharpness", "Sharpness", "sharp"),
    ("vignette", "Vignette", "vignette"),
]
ADJUST_KEYS = [a[0] for a in ADJUSTMENTS]

FILTERS = [
    ("none", "Original", {}),
    ("vivid", "Vivid", {"saturation": 0.35, "contrast": 0.15}),
    ("bright", "Bright", {"exposure": 0.3, "highlights": -0.25, "saturation": 0.1}),
    ("warm", "Warm", {"warmth": 0.45, "saturation": 0.1}),
    ("cool", "Cool", {"warmth": -0.45, "tint": -0.1}),
    ("dramatic", "Dramatic", {"contrast": 0.4, "highlights": -0.35, "shadows": 0.25,
                              "saturation": -0.1, "vignette": 0.35}),
    ("fade", "Fade", {"contrast": -0.35, "shadows": 0.35, "saturation": -0.15}),
    ("vintage", "Vintage", {"warmth": 0.3, "saturation": -0.35, "contrast": -0.15,
                            "shadows": 0.2, "vignette": 0.35}),
    ("mono", "Mono", {"saturation": -1.0}),
    ("noir", "Noir", {"saturation": -1.0, "contrast": 0.5, "shadows": -0.3, "vignette": 0.3}),
]
FILTER_PRESETS = {name: preset for name, _label, preset in FILTERS}

ASPECTS = {"free": 0, "original": -1, "1:1": 1.0, "4:3": 4 / 3, "3:4": 3 / 4,
           "16:9": 16 / 9, "9:16": 9 / 16}

SAVE_FORMATS = {
    ".jpg": "JPEG", ".jpeg": "JPEG", ".png": "PNG", ".webp": "WEBP",
    ".tif": "TIFF", ".tiff": "TIFF", ".bmp": "BMP", ".gif": "GIF",
    ".heic": "HEIF", ".heif": "HEIF",
}
EXIF_FORMATS = {"JPEG", "PNG", "WEBP", "TIFF", "HEIF"}


class EditError(Exception):
    pass


# ---- pure image pipeline (thread-safe, used by tests) -----------------------------
def normalize_mode(im: Image.Image) -> Image.Image:
    if im.mode in ("RGB", "RGBA"):
        return im
    if im.mode in ("LA", "PA") or (im.mode == "P" and "transparency" in im.info):
        return im.convert("RGBA")
    return im.convert("RGB")


def _straighten(im: Image.Image, degrees: float) -> Image.Image:
    """Rotate by `degrees` (clockwise) and zoom in so no empty corners show; keeps size."""
    w, h = im.size
    t = math.radians(abs(degrees))
    scale = max(math.cos(t) + (h / w) * math.sin(t), (w / h) * math.sin(t) + math.cos(t))
    rotated = im.rotate(-degrees, resample=Image.BICUBIC, expand=False)
    cw, ch = w / scale, h / scale
    box = ((w - cw) / 2, (h - ch) / 2, (w + cw) / 2, (h + ch) / 2)
    return rotated.resize((w, h), Image.BICUBIC, box=box)


def apply_geometry(im: Image.Image, p: dict, crop=True) -> Image.Image:
    rot = int(p.get("rotate", 0)) % 360
    if rot:
        im = im.transpose({90: Image.Transpose.ROTATE_90, 180: Image.Transpose.ROTATE_180,
                           270: Image.Transpose.ROTATE_270}[rot])
    if p.get("flipH"):
        im = im.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    if p.get("flipV"):
        im = im.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    angle = float(p.get("straighten", 0.0))
    if abs(angle) > 0.01:
        im = _straighten(im, angle)
    if crop:
        x, y, w, h = p.get("crop", FULL_CROP)
        if [round(v, 5) for v in (x, y, w, h)] != FULL_CROP:
            W, H = im.size
            box = (round(x * W), round(y * H), round((x + w) * W), round((y + h) * H))
            if box[2] - box[0] >= 1 and box[3] - box[1] >= 1:
                im = im.crop(box)
    return im


def effective_adjustments(p: dict) -> dict:
    adj = {k: float(p.get(k, 0.0)) for k in ADJUST_KEYS}
    strength = float(p.get("filterStrength", 1.0))
    for k, v in FILTER_PRESETS.get(p.get("filter", "none"), {}).items():
        adj[k] += v * strength
    return {k: max(-1.0, min(1.0, v)) for k, v in adj.items()}


def _tone_lut(adj: dict) -> list[int]:
    exposure = 2 ** (adj["exposure"] * 1.5)
    contrast = 1 + adj["contrast"] * (0.8 if adj["contrast"] > 0 else 0.6)
    bright, hi, sh = adj["brightness"] * 0.3, adj["highlights"], adj["shadows"]
    warm, tint = adj["warmth"], adj["tint"]
    gains = (1 + 0.16 * warm, 1 - 0.12 * tint, 1 - 0.16 * warm)
    base = []
    for x in range(256):
        v = x / 255 * exposure + bright
        v = min(max(v, 0.0), 1.0)
        v += sh * 0.45 * 4 * v * (1 - v) ** 2      # mostly affects the darker third
        v += hi * 0.45 * 4 * v * v * (1 - v)       # mostly affects the brighter third
        v = (v - 0.5) * contrast + 0.5
        base.append(v)
    lut = []
    for gain in gains:
        lut += [int(round(min(max(v * gain, 0.0), 1.0) * 255)) for v in base]
    return lut


def apply_adjustments(im: Image.Image, p: dict) -> Image.Image:
    adj = effective_adjustments(p)
    if not any(abs(v) > 1e-4 for v in adj.values()):
        return im
    alpha = im.getchannel("A") if im.mode == "RGBA" else None
    rgb = im.convert("RGB") if alpha is not None else im
    if any(abs(adj[k]) > 1e-4 for k in ("brightness", "exposure", "contrast",
                                        "highlights", "shadows", "warmth", "tint")):
        rgb = rgb.point(_tone_lut(adj))
    if abs(adj["saturation"]) > 1e-4:
        rgb = ImageEnhance.Color(rgb).enhance(1 + adj["saturation"])
    s = adj["sharpness"]
    if s > 1e-4:
        radius = max(1.0, min(rgb.size) / 800)
        rgb = rgb.filter(ImageFilter.UnsharpMask(radius=radius, percent=int(180 * s), threshold=2))
    elif s < -1e-4:
        rgb = rgb.filter(ImageFilter.GaussianBlur(radius=-s * max(1.0, min(rgb.size) / 300)))
    v = adj["vignette"]
    if abs(v) > 1e-4:
        mask = Image.radial_gradient("L").resize(rgb.size, Image.BILINEAR)
        mask = mask.point(lambda m: int(min(255, max(0, (m - 70) * 1.5)) * abs(v)))
        fill = Image.new("RGB", rgb.size, (0, 0, 0) if v > 0 else (255, 255, 255))
        rgb = Image.composite(fill, rgb, mask)
    if alpha is not None:
        rgb.putalpha(alpha)
    return rgb


def render(im: Image.Image, p: dict, crop=True) -> Image.Image:
    return apply_adjustments(apply_geometry(im, p, crop), p)


def to_qimage(im: Image.Image) -> QImage:
    if im.mode == "RGBA":
        data, fmt, bpp = im.tobytes("raw", "RGBA"), QImage.Format_RGBA8888, 4
    else:
        im = im.convert("RGB") if im.mode != "RGB" else im
        data, fmt, bpp = im.tobytes("raw", "RGB"), QImage.Format_RGB888, 3
    return QImage(data, im.width, im.height, im.width * bpp, fmt).copy()


def is_default(p: dict) -> bool:
    return all(_same(p.get(k), v) for k, v in DEFAULTS.items() if k != "aspect")


def _same(a, b) -> bool:
    if isinstance(b, list):
        return [round(x, 5) for x in a] == [round(x, 5) for x in b]
    if isinstance(b, float):
        return abs(float(a) - b) < 1e-4
    return a == b


# ---- files -----------------------------------------------------------------------------
def backup_path(path: str):
    digest = hashlib.sha1(path.encode("utf-8", "surrogateescape")).hexdigest()
    return ORIGINALS_DIR / (digest + os.path.splitext(path)[1].lower())


def has_original(path: str) -> bool:
    return bool(path) and backup_path(path).exists()


def copy_name(path: str) -> str:
    stem, ext = os.path.splitext(path)
    candidate, n = f"{stem}_edited{ext}", 2
    while os.path.exists(candidate):
        candidate = f"{stem}_edited_{n}{ext}"
        n += 1
    return candidate


def load_source(path: str, max_side: int | None = None) -> tuple[Image.Image, Image.Exif, dict]:
    with Image.open(path) as im:
        if getattr(im, "n_frames", 1) > 1 and im.format in ("GIF", "WEBP", "PNG"):
            raise EditError("Animated images can't be edited")
        exif = im.getexif()
        info = {k: im.info[k] for k in ("icc_profile",) if im.info.get(k)}
        if max_side:
            im.draft("RGB", (max_side, max_side))
        im = ImageOps.exif_transpose(im)
        im = normalize_mode(im)
        if max_side and max(im.size) > max_side:
            im.thumbnail((max_side, max_side), Image.BICUBIC, reducing_gap=2.0)
        else:
            im.load()
    return im, exif, info


def _exif_bytes(exif: Image.Exif, taken: int, size) -> bytes:
    exif = copy.copy(exif) if exif is not None else Image.Exif()
    exif[274] = 1  # pixels are already upright
    sub = exif.get_ifd(0x8769)
    if not sub.get(36867) and taken:
        try:
            sub[36867] = datetime.fromtimestamp(taken).strftime("%Y:%m:%d %H:%M:%S")
        except (OverflowError, OSError, ValueError):
            pass
    sub[40962], sub[40963] = size
    return exif.tobytes()


def write_image(im: Image.Image, dest: str, exif: Image.Exif, info: dict, taken: int,
                keep_mtime: float | None) -> None:
    """Encode im into dest atomically, keeping EXIF (date!) and the colour profile."""
    ext = os.path.splitext(dest)[1].lower()
    fmt = SAVE_FORMATS.get(ext)
    if fmt is None:
        raise EditError(f"Saving {ext or 'this'} files is not supported")
    if fmt == "JPEG" or fmt == "BMP":
        im = im.convert("RGB")
    if fmt == "GIF":
        im = im.convert("P", palette=Image.Palette.ADAPTIVE)
    kwargs = {}
    if fmt in ("JPEG", "WEBP", "HEIF"):
        kwargs["quality"] = 95 if fmt != "HEIF" else 92
    if fmt == "JPEG":
        kwargs["subsampling"] = 0
    if fmt == "TIFF":
        kwargs["compression"] = "tiff_deflate"
    if info.get("icc_profile") and fmt in ("JPEG", "PNG", "WEBP", "TIFF"):
        kwargs["icc_profile"] = info["icc_profile"]
    if fmt in EXIF_FORMATS:
        kwargs["exif"] = _exif_bytes(exif, taken, im.size)

    folder, name = os.path.split(dest)
    tmp = os.path.join(folder, f".{name}.onegallery-tmp{ext}")
    try:
        try:
            im.save(tmp, fmt, **kwargs)
        except (TypeError, ValueError, KeyError) as exc:
            if "exif" not in kwargs:
                raise
            log.info("saving without EXIF (%s)", exc)
            kwargs.pop("exif")
            im.save(tmp, fmt, **kwargs)
        if os.path.exists(dest):
            shutil.copymode(dest, tmp)
        os.replace(tmp, dest)
    except KeyError as exc:
        raise EditError(f"Saving {ext} files needs an encoder that is not installed") from exc
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    if keep_mtime is not None and "exif" not in kwargs:
        # no EXIF in this format: keep the date the gallery sorts by
        os.utime(dest, (keep_mtime, keep_mtime))


def _refresh_row(path: str) -> None:
    st = os.stat(path)
    with Image.open(path) as im:
        w, h = im.size
    with db.connect() as conn:
        conn.execute(
            "UPDATE images SET mtime = ?, size = ?, width = ?, height = ?, available = 1, "
            "faces_ver = 0 WHERE path = ?", (st.st_mtime, st.st_size, w, h, path))


def save_job(source: str, dest: str, params: dict, row: dict, overwrite: bool) -> str:
    """Runs in a worker: render at full resolution and write. Returns dest."""
    im, exif, info = load_source(source)
    out = render(im, params)
    if overwrite:
        ORIGINALS_DIR.mkdir(parents=True, exist_ok=True)
        backup = backup_path(source)
        if not backup.exists():
            shutil.copy2(source, backup)
    row = row or {}
    write_image(out, dest, exif, info, row.get("taken", 0), row.get("mtime"))
    if overwrite:
        _refresh_row(dest)
    elif row.get("root"):
        st = os.stat(dest)
        meta = read_metadata(dest, st.st_mtime)
        lat, lon = (meta.lat, meta.lon) if meta else (None, None)
        with db.connect() as conn:
            conn.execute(UPSERT, (dest, row["root"], os.path.dirname(dest), os.path.basename(dest),
                                  row["taken"], st.st_mtime, st.st_size, out.width, out.height,
                                  lat, lon, 0, 0.0))
    return dest


def revert_job(path: str) -> str:
    backup = backup_path(path)
    if not backup.exists():
        raise EditError("No saved original for this picture")
    shutil.copy2(backup, path)  # copy2 restores the original modification time too
    backup.unlink()
    _refresh_row(path)
    return path


def originals_size() -> int:
    total = 0
    if ORIGINALS_DIR.exists():
        for f in ORIGINALS_DIR.iterdir():
            try:
                total += f.stat().st_size
            except OSError:
                pass
    return total


# ---- Qt side --------------------------------------------------------------------------------
class EditImageProvider(QQuickImageProvider):
    """image://edit/preview/<rev>, image://edit/original/<rev>, image://edit/filter/<name>/<rev>"""

    def __init__(self, editor):
        super().__init__(QQuickImageProvider.ImageType.Image)
        self.editor = editor

    def requestImage(self, image_id, size, requested_size):
        parts = image_id.split("/")
        image = QImage()
        if parts[0] == "preview":
            image = self.editor.preview_image
        elif parts[0] == "original":
            image = self.editor.original_image
        elif parts[0] == "filter" and len(parts) > 1:
            image = self.editor.filter_images.get(parts[1], QImage())
        if size is not None:
            size.setWidth(image.width())
            size.setHeight(image.height())
        return image


class Editor(QObject):
    """The editing session shown by EditorPage.qml (one picture at a time)."""

    stateChanged = Signal()
    paramsChanged = Signal()
    previewChanged = Signal()
    filtersChanged = Signal()
    historyChanged = Signal()
    originalsSizeChanged = Signal()
    message = Signal(str)
    saved = Signal(str, bool)      # path, is_copy
    reverted = Signal(str)
    libraryChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._path = ""
        self._row: dict = {}
        self._params = copy.deepcopy(DEFAULTS)
        self._history = [copy.deepcopy(DEFAULTS)]
        self._hpos = 0
        self._crop_mode = False
        self._loading = False
        self._saving = False
        self._error = ""
        self._session = 0
        self._base = None            # preview-size PIL image
        self._small = None           # filter thumbnail base
        self._rendering = False
        self._render_again = False
        self._revision = 0
        self._filter_revision = 0
        self._originals_size = ""
        self.preview_image = QImage()
        self.original_image = QImage()
        self.filter_images: dict[str, QImage] = {}

    # ---- session -------------------------------------------------------------------
    @Slot(str)
    def open(self, path):
        self._session += 1
        session = self._session
        self._path = path
        self._row = {}
        self._params = copy.deepcopy(DEFAULTS)
        self._history = [copy.deepcopy(DEFAULTS)]
        self._hpos = 0
        self._crop_mode = False
        self._base = self._small = None
        self.preview_image = QImage()
        self.original_image = QImage()
        self.filter_images = {}
        self._error = ""
        self._loading = True
        self.stateChanged.emit()
        self.paramsChanged.emit()
        self.historyChanged.emit()

        def load(path):
            base, _exif, _info = load_source(path, PREVIEW_MAX)
            small = ImageOps.fit(base, (FILTER_THUMB, FILTER_THUMB), Image.BICUBIC)
            row = db.connect().execute(
                "SELECT root, dir, taken, mtime FROM images WHERE path = ?", (path,)).fetchone()
            if row:
                row = dict(zip(("root", "dir", "taken", "mtime"), row))
            else:  # not in the library (opened from a file manager)
                mtime = os.stat(path).st_mtime
                meta = read_metadata(path, mtime)
                row = {"taken": meta[0] if meta else int(mtime), "mtime": mtime}
            return base, small, to_qimage(base), row

        def done(result):
            if session != self._session:
                return
            self._base, self._small, self.original_image, self._row = result
            self._loading = False
            self.stateChanged.emit()
            self._request_render()
            self._render_filters()

        def failed(exc):
            if session != self._session:
                return
            self._loading = False
            self._error = str(exc) if isinstance(exc, EditError) else "This picture can't be opened for editing"
            self.stateChanged.emit()
            self.message.emit(self._error)

        run_async(load, path, on_done=done, on_error=failed)

    @Slot()
    def close(self):
        self._session += 1
        self._path = ""
        self._base = self._small = None
        self.preview_image = QImage()
        self.original_image = QImage()
        self.filter_images = {}
        self._loading = self._saving = False
        self.stateChanged.emit()

    # ---- rendering -----------------------------------------------------------------
    def _request_render(self):
        if self._base is None:
            return
        if self._rendering:
            self._render_again = True
            return
        self._rendering = True
        session = self._session
        params = copy.deepcopy(self._params)
        crop = not self._crop_mode

        def work(base, params, crop):
            return to_qimage(render(base, params, crop))

        def done(image):
            self._rendering = False
            if session != self._session:
                return
            self.preview_image = image
            self._revision += 1
            self.previewChanged.emit()
            if self._render_again:
                self._render_again = False
                self._request_render()

        def failed(_exc):
            self._rendering = False

        run_async(work, self._base, params, crop, on_done=done, on_error=failed)

    def _render_filters(self):
        if self._small is None:
            return
        session = self._session
        geometry = {k: self._params[k] for k in ("rotate", "flipH", "flipV")}

        def work(small, geometry):
            base = apply_geometry(small, geometry, crop=False)
            return {name: to_qimage(apply_adjustments(base, {"filter": name, "filterStrength": 1.0}))
                    for name, _label, _preset in FILTERS}

        def done(images):
            if session == self._session:
                self.filter_images = images
                self._filter_revision += 1
                self.filtersChanged.emit()

        run_async(work, self._small, geometry, on_done=done)

    # ---- parameter changes ------------------------------------------------------------
    def _changed(self, commit=True, geometry=False):
        if commit:
            self.commit()
        self.paramsChanged.emit()
        self._request_render()
        if geometry:
            self._render_filters()

    @Slot(str, float)
    def setValue(self, key, value):
        """Live slider update; call commit() when the slider is released."""
        if key not in ADJUST_KEYS and key not in ("filterStrength", "straighten"):
            return
        lo = 0.0 if key == "filterStrength" else (-45.0 if key == "straighten" else -1.0)
        hi = 45.0 if key == "straighten" else 1.0
        self._params[key] = max(lo, min(hi, float(value)))
        self._changed(commit=False)

    @Slot()
    def commit(self):
        if _same_params(self._params, self._history[self._hpos]):
            return
        del self._history[self._hpos + 1:]
        self._history.append(copy.deepcopy(self._params))
        self._hpos = len(self._history) - 1
        self.historyChanged.emit()

    @Slot(str)
    def resetValue(self, key):
        if key in DEFAULTS:
            self._params[key] = copy.deepcopy(DEFAULTS[key])
            self._changed()

    @Slot(str)
    def setFilter(self, name):
        if name in FILTER_PRESETS:
            self._params["filter"] = name
            self._params["filterStrength"] = 1.0
            self._changed()

    @Slot()
    def rotateLeft(self):
        p = self._params
        # with a single flip active the visual rotation runs the other way
        delta = 90 if p["flipH"] == p["flipV"] else -90
        p["rotate"] = (p["rotate"] + delta) % 360
        x, y, w, h = p["crop"]
        p["crop"] = [y, 1 - (x + w), h, w]
        self._fix_aspect_after_rotate()
        self._changed(geometry=True)

    def _fix_aspect_after_rotate(self):
        a = self._params["aspect"]
        if ":" in a:
            l, r = a.split(":")
            swapped = f"{r}:{l}"
            if swapped in ASPECTS:
                self._params["aspect"] = swapped

    @Slot()
    def flipHorizontal(self):
        p = self._params
        p["flipH"] = not p["flipH"]
        p["straighten"] = -p["straighten"]
        x, y, w, h = p["crop"]
        p["crop"] = [1 - x - w, y, w, h]
        self._changed(geometry=True)

    @Slot()
    def flipVertical(self):
        p = self._params
        p["flipV"] = not p["flipV"]
        p["straighten"] = -p["straighten"]
        x, y, w, h = p["crop"]
        p["crop"] = [x, 1 - y - h, w, h]
        self._changed(geometry=True)

    @Slot(float, float, float, float)
    def setCrop(self, x, y, w, h):
        w = max(0.02, min(1.0, w))
        h = max(0.02, min(1.0, h))
        x = max(0.0, min(1.0 - w, x))
        y = max(0.0, min(1.0 - h, y))
        self._params["crop"] = [x, y, w, h]
        self._changed()

    @Slot(str)
    def setAspect(self, name):
        if name not in ASPECTS:
            return
        self._params["aspect"] = name
        ratio = self._aspect_value(name)
        gw, gh = self._geom_size()
        if ratio > 0 and gw:
            # largest centred rectangle with this pixel ratio
            w_px, h_px = gw, gw / ratio
            if h_px > gh:
                h_px, w_px = gh, gh * ratio
            w, h = w_px / gw, h_px / gh
            self._params["crop"] = [(1 - w) / 2, (1 - h) / 2, w, h]
        self._changed()

    def _geom_size(self) -> tuple[int, int]:
        """Pixel size of the preview after rotation (straightening keeps the size)."""
        if self._base is None:
            return (0, 0)
        w, h = self._base.size
        return (h, w) if self._params["rotate"] % 180 == 90 else (w, h)

    def _aspect_value(self, name) -> float:
        value = ASPECTS.get(name, 0)
        if value == -1:
            gw, gh = self._geom_size()
            return gw / gh if gh else 0.0
        return float(value) if value > 0 else 0.0

    @Slot(bool)
    def setCropMode(self, on):
        if on != self._crop_mode:
            self._crop_mode = on
            self.stateChanged.emit()
            self._request_render()

    @Slot()
    def resetAll(self):
        self._params = copy.deepcopy(DEFAULTS)
        self._changed(geometry=True)

    @Slot()
    def undo(self):
        if self._hpos > 0:
            self._hpos -= 1
            self._restore()

    @Slot()
    def redo(self):
        if self._hpos < len(self._history) - 1:
            self._hpos += 1
            self._restore()

    def _restore(self):
        old = self._params
        self._params = copy.deepcopy(self._history[self._hpos])
        self.historyChanged.emit()
        geometry = any(old[k] != self._params[k] for k in ("rotate", "flipH", "flipV"))
        self._changed(commit=False, geometry=geometry)

    # ---- save / revert ---------------------------------------------------------------------
    def _start_save(self, overwrite: bool):
        if not self._path or self._saving or self._base is None:
            return
        source = self._path
        dest = source if overwrite else copy_name(source)
        self._saving = True
        self.stateChanged.emit()

        def done(path):
            self._saving = False
            self.stateChanged.emit()
            self.libraryChanged.emit()
            self.originalsSizeChanged.emit()
            self.message.emit(
                f"Saved as {os.path.basename(path)}" if not overwrite
                else "Saved. You can revert to the original from the ⋮ menu.")
            self.saved.emit(path, not overwrite)

        def failed(exc):
            self._saving = False
            self.stateChanged.emit()
            self.message.emit(str(exc) if isinstance(exc, EditError)
                              else f"Could not save: {exc.__class__.__name__}: {exc}")

        run_async(save_job, source, dest, copy.deepcopy(self._params), dict(self._row), overwrite,
                  on_done=done, on_error=failed)

    @Slot()
    def save(self):
        self._start_save(overwrite=True)

    @Slot()
    def saveCopy(self):
        self._start_save(overwrite=False)

    @Slot("QStringList", bool)
    def quickRotate(self, paths, clockwise):
        """Rotate pictures 90° and save (the original is kept for Revert). Videos are skipped."""
        paths = [p for p in paths if p and not is_video(p)]
        if not paths:
            return
        params = copy.deepcopy(DEFAULTS)
        params["rotate"] = 270 if clockwise else 90

        def work(paths):
            done, failed = [], []
            conn = db.connect()
            for path in paths:
                row = conn.execute("SELECT root, dir, taken, mtime FROM images WHERE path = ?",
                                   (path,)).fetchone()
                row = dict(zip(("root", "dir", "taken", "mtime"), row)) if row else {}
                try:
                    save_job(path, path, params, row, overwrite=True)
                    done.append(path)
                except Exception as exc:
                    log.warning("rotate %s failed: %s", path, exc)
                    failed.append(path)
            return done, failed

        def finished(result):
            done, failed = result
            self.libraryChanged.emit()
            self.originalsSizeChanged.emit()
            if failed:
                self.message.emit(f"Could not rotate {len(failed)} picture(s)")
            elif len(done) > 1:
                self.message.emit(f"Rotated {len(done)} pictures")
            self.saved.emit(done[0] if done else "", False)

        run_async(work, paths, on_done=finished)

    @Slot(str, result=bool)
    def hasOriginal(self, path):
        return has_original(path)

    @Slot(str)
    def revertOriginal(self, path):
        def done(p):
            self.libraryChanged.emit()
            self.originalsSizeChanged.emit()
            self.message.emit("Reverted to the original")
            self.reverted.emit(p)

        def failed(exc):
            self.message.emit(str(exc) if isinstance(exc, EditError) else f"Could not revert: {exc}")

        run_async(revert_job, path, on_done=done, on_error=failed)

    @Slot()
    def refreshOriginalsSize(self):
        def done(size):
            self._originals_size = format_size(size)
            self.originalsSizeChanged.emit()

        run_async(originals_size, on_done=done)

    @Slot()
    def clearOriginals(self):
        def done(_):
            self.message.emit("Saved originals deleted")
            self.refreshOriginalsSize()

        run_async(shutil.rmtree, str(ORIGINALS_DIR), True, on_done=done)

    # ---- properties --------------------------------------------------------------------------
    @Property(str, notify=stateChanged)
    def path(self):
        return self._path

    @Property(bool, notify=stateChanged)
    def loading(self):
        return self._loading

    @Property(bool, notify=stateChanged)
    def saving(self):
        return self._saving

    @Property(str, notify=stateChanged)
    def error(self):
        return self._error

    @Property(bool, notify=stateChanged)
    def cropMode(self):
        return self._crop_mode

    @Property(bool, notify=stateChanged)
    def hasBackup(self):
        return has_original(self._path)

    @Property("QVariantMap", notify=paramsChanged)
    def params(self):
        return self._params

    @Property(bool, notify=paramsChanged)
    def dirty(self):
        return not is_default(self._params)

    @Property(float, notify=paramsChanged)
    def aspectRatio(self):
        return self._aspect_value(self._params["aspect"])

    @Property(bool, notify=historyChanged)
    def canUndo(self):
        return self._hpos > 0

    @Property(bool, notify=historyChanged)
    def canRedo(self):
        return self._hpos < len(self._history) - 1

    @Property(str, notify=previewChanged)
    def previewUrl(self):
        return f"image://edit/preview/{self._revision}" if not self.preview_image.isNull() else ""

    @Property(str, notify=stateChanged)
    def originalUrl(self):
        return f"image://edit/original/{self._session}" if not self.original_image.isNull() else ""

    @Property(int, notify=filtersChanged)
    def filterRevision(self):
        return self._filter_revision

    @Property("QVariantList", constant=True)
    def filters(self):
        return [{"name": n, "label": label} for n, label, _p in FILTERS]

    @Property("QVariantList", constant=True)
    def adjustments(self):
        return [{"key": k, "label": label, "icon": icon} for k, label, icon in ADJUSTMENTS]

    @Property("QStringList", constant=True)
    def aspects(self):
        return list(ASPECTS)

    @Property(str, notify=originalsSizeChanged)
    def originalsSize(self):
        return self._originals_size


def _same_params(a: dict, b: dict) -> bool:
    return all(_same(a.get(k), v) for k, v in b.items())
