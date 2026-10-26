"""Offline place names for GPS-tagged photos (Places in Collections).

Uses the GeoNames "cities15000" list (every town with more than 15,000 people, about 3 MB,
CC BY 4.0, https://www.geonames.org). It is downloaded once on request; lookups then run
entirely offline. Country names come from Qt's locale data.
"""

import io
import logging
import math
import os
import urllib.request
import zipfile

from PySide6.QtCore import QLocale

from . import DATA_DIR, db

log = logging.getLogger(__name__)

GEO_DIR = DATA_DIR / "geo"
CITIES = GEO_DIR / "cities15000.txt"
CITIES_URL = "https://download.geonames.org/export/dump/cities15000.zip"
NEAR_KM = 60          # farther than this from any town: label with the country only
CITY_KM = 12          # within this distance the largest town wins (Lisbon, not a parish of it)
SKIP_CODES = {"PPLX", "PPLH", "PPLQ", "PPLW", "PPLCH"}  # districts, historical, abandoned
USER_AGENT = "One Gallery (+https://github.com/lochansaroy02/onegallery)"


def data_available() -> bool:
    return CITIES.exists() and CITIES.stat().st_size > 100_000


def download(progress=None) -> None:
    """Fetch and unpack the city list. progress(done_bytes, total_bytes)."""
    GEO_DIR.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(CITIES_URL, headers={"User-Agent": USER_AGENT})
    buf = io.BytesIO()
    with urllib.request.urlopen(req, timeout=60) as resp:
        total = int(resp.headers.get("Content-Length") or 0)
        while True:
            chunk = resp.read(64 * 1024)
            if not chunk:
                break
            buf.write(chunk)
            if progress:
                progress(buf.tell(), total)
    with zipfile.ZipFile(buf) as zf:
        data = zf.read("cities15000.txt")
    tmp = CITIES.with_suffix(".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, CITIES)


def country_name(code: str) -> str:
    territory = QLocale.codeToTerritory(code)
    if territory == QLocale.AnyTerritory:
        return code
    return QLocale.territoryToString(territory)


class Geocoder:
    """Nearest-town lookup on a 1° grid."""

    def __init__(self, path=CITIES):
        self.grid: dict[tuple[int, int], list] = {}
        with open(path, encoding="utf-8") as f:
            for line in f:
                cols = line.rstrip("\n").split("\t")
                if len(cols) < 15:
                    continue
                if cols[7] in SKIP_CODES:
                    continue
                try:
                    lat, lon = float(cols[4]), float(cols[5])
                    population = int(cols[14] or 0)
                except ValueError:
                    continue
                key = (math.floor(lat), math.floor(lon))
                self.grid.setdefault(key, []).append((lat, lon, cols[1], cols[8], population))

    @staticmethod
    def _km(lat1, lon1, lat2, lon2):
        x = math.radians(lon2 - lon1) * math.cos(math.radians((lat1 + lat2) / 2))
        y = math.radians(lat2 - lat1)
        return 6371 * math.hypot(x, y)

    def nearest(self, lat: float, lon: float):
        """(name, country code, distance km) of the town a point belongs to, or None.

        The largest town within CITY_KM wins; otherwise the nearest one."""
        cy, cx = math.floor(lat), math.floor(lon)
        for radius in (1, 3):
            nearest, biggest = None, None
            for dy in range(-radius, radius + 1):
                for dx in range(-radius, radius + 1):
                    gx = ((cx + dx + 180) % 360) - 180
                    for c in self.grid.get((cy + dy, gx), ()):
                        d = self._km(lat, lon, c[0], c[1])
                        if nearest is None or d < nearest[2]:
                            nearest = (c[2], c[3], d)
                        if d <= CITY_KM and (biggest is None or c[4] > biggest[3]):
                            biggest = (c[2], c[3], d, c[4])
            if biggest is not None:
                return biggest[:3]
            if nearest is not None:
                return nearest
        return None

    def place(self, lat: float, lon: float) -> tuple[str, str]:
        """(place, country name). place falls back to the country far from any town."""
        hit = self.nearest(lat, lon)
        if hit is None:
            return ("Unknown place", "")
        name, code, dist = hit
        country = country_name(code)
        return (name if dist <= NEAR_KM else country, country)


def assign_places(batch=2000) -> int:
    """Give every GPS-tagged picture without a place its nearest town. Runs in a worker."""
    if not data_available():
        return 0
    conn = db.connect()
    rows = conn.execute(
        "SELECT id, lat, lon FROM images WHERE lat IS NOT NULL AND place IS NULL").fetchall()
    if not rows:
        return 0
    geocoder = Geocoder()
    updates = []
    for iid, lat, lon in rows:
        place, country = geocoder.place(lat, lon)
        updates.append((place, country, iid))
        if len(updates) >= batch:
            with conn:
                conn.executemany("UPDATE images SET place = ?, country = ? WHERE id = ?", updates)
            updates.clear()
    if updates:
        with conn:
            conn.executemany("UPDATE images SET place = ?, country = ? WHERE id = ?", updates)
    return len(rows)
