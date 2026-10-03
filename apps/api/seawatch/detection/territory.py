"""TERRITORY factor: which maritime zone of Taiwan a position is in.

Zones, measured from Taiwan-administered land (main island, Kinmen, Penghu, Matsu, Lanyu, Green Island, ...):

    TS   territorial sea      <= 12 nm   sovereignty; a foreign survey vessel here is the clearest breach
                              (cut at the median line to the mainland, so Kinmen's 12 nm does not swallow Xiamen harbour)
    CZ   contiguous zone      12-24 nm   enforcement zone
    EEZ  exclusive economic   24-200 nm, and nearer to Taiwan than to the mainland / Japan / the Philippines
                              (an equidistance APPROXIMATION of the median lines; the real limits are negotiated)
    OUT  anything else

Geometry comes from public-domain Natural Earth coastlines (see scripts/build_taiwan_geo.py). It is a reference, NOT the legal
baseline system: distances can be off by a few nautical miles near straits and island groups. Positions in hourly feeds carry
~3 nm of their own uncertainty, so callers should treat a position within a few nm of a limit as "on the line".
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import numpy as np

NM = 1852.0
TS_NM, CZ_NM, EEZ_NM = 12.0, 24.0, 200.0
CODE = {"OUT": 0, "EEZ": 1, "CZ": 2, "TS": 3}
NAME = {v: k for k, v in CODE.items()}
LABEL = {"TS": "territorial sea (<= 12 nm)", "CZ": "contiguous zone (12-24 nm)", "EEZ": "exclusive economic zone (approx.)", "OUT": "outside Taiwan's claimed waters"}

GRID_DEG = 0.05
LON0, LON1, LAT0, LAT1 = 112.0, 130.0, 16.0, 32.0


class Territory:
    def __init__(self, tw_land, other_land):
        import pyproj
        import shapely
        from shapely.ops import transform

        proj = pyproj.Transformer.from_crs("EPSG:4326", "+proj=aeqd +lat_0=23.7 +lon_0=121.0 +units=m +datum=WGS84", always_xy=True)
        self._proj = proj
        tw = transform(proj.transform, tw_land)
        oth = transform(proj.transform, other_land)
        lons = np.arange(LON0, LON1 + 1e-9, GRID_DEG)
        lats = np.arange(LAT0, LAT1 + 1e-9, GRID_DEG)
        self._lons, self._lats = lons, lats
        gx, gy = np.meshgrid(lons, lats)
        x, y = proj.transform(gx.ravel(), gy.ravel())
        pts = shapely.points(x, y)
        d_tw = shapely.distance(pts, tw) / NM
        d_ot = shapely.distance(pts, oth) / NM
        on_land = shapely.contains(tw, pts) | shapely.contains(oth, pts)
        zone = np.zeros(d_tw.shape, np.int8)
        nearer = d_tw <= d_ot  # the median line to the mainland / Japan / Philippines is the practical limit on every side
        zone[(d_tw <= EEZ_NM) & nearer] = CODE["EEZ"]
        zone[(d_tw <= CZ_NM) & nearer] = CODE["CZ"]
        zone[(d_tw <= TS_NM) & nearer] = CODE["TS"]
        zone[shapely.contains(tw, pts)] = CODE["TS"]
        shape2 = gx.shape
        self.dist_nm = d_tw.reshape(shape2).astype(np.float32)
        self.zone = zone.reshape(shape2)
        self.land = on_land.reshape(shape2)

    # ----------------------------------------------------------------------- #
    @classmethod
    @lru_cache(maxsize=1)
    def default(cls) -> "Territory | None":
        from shapely.geometry import shape

        root = Path(__file__).resolve().parents[4] / "data" / "geo"
        try:
            tw = shape(json.loads((root / "taiwan_land.geojson").read_text(encoding="utf8"))["features"][0]["geometry"])
            ot = shape(json.loads((root / "neighbour_land.geojson").read_text(encoding="utf8"))["features"][0]["geometry"])
        except (OSError, ValueError, KeyError):
            return None
        return cls(tw, ot)

    def _idx(self, lat, lon):
        lat, lon = np.asarray(lat, float), np.asarray(lon, float)
        j = np.clip(np.rint((lon - LON0) / GRID_DEG).astype(int), 0, len(self._lons) - 1)
        i = np.clip(np.rint((lat - LAT0) / GRID_DEG).astype(int), 0, len(self._lats) - 1)
        return i, j

    def code_at(self, lat, lon) -> np.ndarray:
        i, j = self._idx(lat, lon)
        return self.zone[i, j]

    def zone_at(self, lat: float, lon: float) -> str:
        return NAME[int(self.code_at(np.array([lat]), np.array([lon]))[0])]

    def distance_nm(self, lat, lon) -> np.ndarray:
        """Distance (nm) to the nearest Taiwan-administered land."""

        i, j = self._idx(lat, lon)
        return self.dist_nm[i, j]

    def summarise(self, lat: np.ndarray, lon: np.ndarray) -> dict[str, float]:
        """Fractions of fixes in each zone, nearest approach, and an on-the-line flag for a stretch of track."""

        c = self.code_at(lat, lon)
        d = self.distance_nm(lat, lon)
        n = max(len(c), 1)
        out = {k: float(np.sum(c == v) / n) for k, v in CODE.items()}
        out["n_ts"], out["n_cz"], out["n_eez"] = int(np.sum(c == 3)), int(np.sum(c == 2)), int(np.sum(c == 1))
        out["nearest_nm"] = float(np.min(d)) if len(d) else float("nan")
        return out
