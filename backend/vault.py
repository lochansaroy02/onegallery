"""Encrypted storage for the private album.

Layout (in ~/.local/share/onegallery/private/, folder mode 0700):

    vault.json       KDF parameters + the album key wrapped (encrypted) with the password
    manifest.bin     encrypted JSON: one entry per item (name, original path, date, size, ...)
    items/<id>.bin   the encrypted file
    items/<id>.thumb the encrypted thumbnail (JPEG)

The album key is 32 random bytes. The password is stretched with scrypt (N=2^15, r=8, p=1)
into a key-encryption key that wraps it with AES-256-GCM, so changing the password only
re-wraps the album key. Files are encrypted with AES-256-GCM in 1 MiB chunks; each chunk's
nonce and associated data carry the item id, the chunk number and a "last chunk" flag, so
chunks can't be swapped, reordered or cut off without decryption failing.

There is no recovery: without the password the files can't be decrypted.
"""

import base64
import hashlib
import json
import os
import shutil
import struct
import threading
import time
import uuid
from pathlib import Path

try:
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    AVAILABLE = True
    IMPORT_ERROR = ""
except ImportError as exc:  # python-cryptography not installed (or not bundled)
    AESGCM = None
    InvalidTag = Exception
    AVAILABLE = False
    IMPORT_ERROR = str(exc)

VERSION = 1
MAGIC = b"LGV1"
CHUNK = 1 << 20
TAG = 16
KDF = {"n": 2 ** 15, "r": 8, "p": 1}
# These keep the app's old name (LGallery) on purpose: they are part of the encryption, and
# changing them would make existing private albums unreadable.
KEY_AAD = b"lgallery-private-album-key"
MANIFEST_AAD = b"lgallery-private-album-manifest"


class VaultError(Exception):
    pass


class WrongPassword(VaultError):
    expected = True   # a user mistake, not a bug: logged without a traceback


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.b64decode(text.encode("ascii"))


def _kek(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p,
                          maxmem=256 * 1024 * 1024, dklen=32)


def _write_atomic(path: Path, data: bytes) -> None:
    tmp = path.with_name(path.name + ".part")
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    os.replace(tmp, path)


class Vault:
    """Thread-safe. All item operations need the vault to be unlocked."""

    def __init__(self, root):
        self.root = Path(root)
        self.items_dir = self.root / "items"
        self.meta_path = self.root / "vault.json"
        self.manifest_path = self.root / "manifest.bin"
        self._key: bytes | None = None
        self._manifest: dict | None = None
        self._lock = threading.RLock()

    # ---- state ------------------------------------------------------------------------------
    @property
    def exists(self) -> bool:
        return self.meta_path.exists()

    @property
    def unlocked(self) -> bool:
        return self._key is not None

    def _require(self) -> tuple[bytes, dict]:
        key, manifest = self._key, self._manifest
        if key is None or manifest is None:
            raise VaultError("The private album is locked")
        return key, manifest

    def _need_crypto(self):
        if not AVAILABLE:
            raise VaultError("The private album needs python-cryptography")

    # ---- password ---------------------------------------------------------------------------
    def _wrap(self, key: bytes, password: str) -> dict:
        salt = os.urandom(16)
        nonce = os.urandom(12)
        kek = _kek(password, salt, **KDF)
        wrapped = AESGCM(kek).encrypt(nonce, key, KEY_AAD)
        return {"version": VERSION, "kdf": "scrypt", **KDF, "salt": _b64(salt),
                "nonce": _b64(nonce), "key": _b64(wrapped), "changed": int(time.time())}

    def _unwrap(self, password: str) -> bytes:
        try:
            meta = json.loads(self.meta_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise VaultError("There is no private album yet") from None
        except (OSError, ValueError) as exc:
            raise VaultError(f"The private album's key file is damaged: {exc}") from exc
        if meta.get("version") != VERSION or meta.get("kdf") != "scrypt":
            raise VaultError("This private album was made by a newer One Gallery")
        kek = _kek(password, _unb64(meta["salt"]), meta["n"], meta["r"], meta["p"])
        try:
            return AESGCM(kek).decrypt(_unb64(meta["nonce"]), _unb64(meta["key"]), KEY_AAD)
        except InvalidTag:
            raise WrongPassword("Wrong password") from None

    def create(self, password: str) -> None:
        self._need_crypto()
        with self._lock:
            if self.exists:
                raise VaultError("The private album already exists")
            self.items_dir.mkdir(parents=True, exist_ok=True)
            for d in (self.root, self.items_dir):
                try:
                    os.chmod(d, 0o700)
                except OSError:
                    pass
            key = AESGCM.generate_key(bit_length=256)
            self._key, self._manifest = key, {"version": VERSION, "items": {}}
            self._save_manifest()
            _write_atomic(self.meta_path, json.dumps(self._wrap(key, password)).encode("utf-8"))

    def unlock(self, password: str) -> None:
        self._need_crypto()
        key = self._unwrap(password)
        with self._lock:
            self._key = key
            try:
                self._manifest = self._load_manifest()
            except Exception:
                self._key = None
                raise

    def lock(self) -> None:
        with self._lock:
            self._key = None
            self._manifest = None

    def check_password(self, password: str) -> bool:
        try:
            self._unwrap(password)
            return True
        except WrongPassword:
            return False

    def change_password(self, old: str, new: str) -> None:
        self._need_crypto()
        with self._lock:
            key = self._unwrap(old)
            _write_atomic(self.meta_path, json.dumps(self._wrap(key, new)).encode("utf-8"))

    def destroy(self) -> None:
        """Delete the private album and everything in it (no password needed)."""
        with self._lock:
            self.lock()
            shutil.rmtree(self.root, ignore_errors=True)

    # ---- manifest ---------------------------------------------------------------------------------
    def _load_manifest(self) -> dict:
        key = self._key
        if not self.manifest_path.exists():
            return {"version": VERSION, "items": {}}
        blob = self.manifest_path.read_bytes()
        try:
            data = AESGCM(key).decrypt(blob[:12], blob[12:], MANIFEST_AAD)
        except InvalidTag:
            raise VaultError("The private album's list is damaged") from None
        return json.loads(data.decode("utf-8"))

    def _save_manifest(self) -> None:
        key, manifest = self._require()
        nonce = os.urandom(12)
        data = json.dumps(manifest, separators=(",", ":")).encode("utf-8")
        _write_atomic(self.manifest_path, nonce + AESGCM(key).encrypt(nonce, data, MANIFEST_AAD))

    def items(self) -> list[dict]:
        with self._lock:
            _key, manifest = self._require()
            return [dict(v, id=k) for k, v in manifest["items"].items()]

    def item(self, item_id: str) -> dict:
        with self._lock:
            _key, manifest = self._require()
            try:
                return dict(manifest["items"][item_id], id=item_id)
            except KeyError:
                raise VaultError("Not in the private album") from None

    # ---- items --------------------------------------------------------------------------------------
    @staticmethod
    def _nonce(prefix: bytes, index: int) -> bytes:
        return prefix + struct.pack(">I", index)

    @staticmethod
    def _aad(item_id: str, index: int, last: bool) -> bytes:
        return item_id.encode("ascii") + struct.pack(">I?", index, last)

    def _encrypt_file(self, src: str, dest: Path, item_id: str, key: bytes) -> None:
        aes = AESGCM(key)
        prefix = os.urandom(8)
        tmp = dest.with_name(dest.name + ".part")
        try:
            with open(src, "rb") as fin, open(tmp, "wb") as fout:
                fout.write(MAGIC + prefix)
                index, chunk = 0, fin.read(CHUNK)
                while True:
                    following = fin.read(CHUNK) if len(chunk) == CHUNK else b""
                    last = not following
                    fout.write(aes.encrypt(self._nonce(prefix, index), chunk, self._aad(item_id, index, last)))
                    if last:
                        break
                    index, chunk = index + 1, following
                fout.flush()
                os.fsync(fout.fileno())
            os.replace(tmp, dest)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise

    def _decrypt_chunks(self, item_id: str):
        key, _manifest = self._require()
        aes = AESGCM(key)
        path = self.items_dir / f"{item_id}.bin"
        size = path.stat().st_size - len(MAGIC) - 8
        blocks = max(1, -(-size // (CHUNK + TAG)))
        with open(path, "rb") as f:
            head = f.read(len(MAGIC) + 8)
            if head[:4] != MAGIC:
                raise VaultError("Not a private album file")
            prefix = head[4:]
            for index in range(blocks):
                block = f.read(CHUNK + TAG)
                try:
                    yield aes.decrypt(self._nonce(prefix, index), block,
                                      self._aad(item_id, index, index == blocks - 1))
                except InvalidTag:
                    raise VaultError("This private file is damaged") from None

    def add(self, src: str, meta: dict, thumbnail: bytes) -> str:
        """Encrypt src (and its JPEG thumbnail) into the album. Returns the new item id.

        The original is left alone; the caller removes it once this succeeded."""
        key, _manifest = self._require()
        item_id = uuid.uuid4().hex
        data_path = self.items_dir / f"{item_id}.bin"
        thumb_path = self.items_dir / f"{item_id}.thumb"
        self.items_dir.mkdir(parents=True, exist_ok=True)
        try:
            self._encrypt_file(src, data_path, item_id, key)
            nonce = os.urandom(12)
            _write_atomic(thumb_path, nonce + AESGCM(key).encrypt(nonce, thumbnail, b"thumb" + item_id.encode()))
            with self._lock:
                _key, manifest = self._require()
                manifest["items"][item_id] = dict(meta, added=int(time.time()))
                self._save_manifest()
        except BaseException:
            data_path.unlink(missing_ok=True)
            thumb_path.unlink(missing_ok=True)
            raise
        return item_id

    def read_bytes(self, item_id: str) -> bytes:
        return b"".join(self._decrypt_chunks(item_id))

    def read_thumbnail(self, item_id: str) -> bytes:
        key, _manifest = self._require()
        blob = (self.items_dir / f"{item_id}.thumb").read_bytes()
        try:
            return AESGCM(key).decrypt(blob[:12], blob[12:], b"thumb" + item_id.encode())
        except InvalidTag:
            raise VaultError("This private thumbnail is damaged") from None

    def decrypt_to(self, item_id: str, dest) -> None:
        dest = Path(dest)
        tmp = dest.with_name(dest.name + ".part")
        try:
            with open(tmp, "wb") as f:
                for chunk in self._decrypt_chunks(item_id):
                    f.write(chunk)
            os.replace(tmp, dest)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise

    def remove(self, item_id: str) -> None:
        with self._lock:
            _key, manifest = self._require()
            manifest["items"].pop(item_id, None)
            self._save_manifest()
        for suffix in (".bin", ".thumb"):
            (self.items_dir / f"{item_id}{suffix}").unlink(missing_ok=True)
