"""Submarine cable routes near Taiwan (TeleGeography public map, CC BY-NC-SA 4.0) and distance-to-cable lookup.

Public depictions are approximate; they show where cables are, not where they lie to survey accuracy.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import numpy as np

from .territory import GRID_DEG, LAT0, LAT1, LON0, LON1, NM

ROOT = Path(__file__).resolve().parents[4] / "data" / "geo"


class Cables:
    def __init__(self, features: list[dict]):
        import pyproj
        import shapely
        from shapely.geometry import shape
        from shapely.ops import transform

        proj = pyproj.Transformer.from_crs("EPSG:4326", "+proj=aeqd +lat_0=23.7 +lon_0=121.0 +units=m +datum=WGS84", always_xy=True)
        self.names = [f["properties"]["name"] for f in features]
        lines = [transform(proj.transform, shape(f["geometry"])) for f in features]
        lons = np.arange(LON0, LON1 + 1e-9, GRID_DEG)
        lats = np.arange(LAT0, LAT1 + 1e-9, GRID_DEG)
        self._lons, self._lats = lons, lats
        gx, gy = np.meshgrid(lons, lats)
        x, y = proj.transform(gx.ravel(), gy.ravel())
        pts = shapely.points(x, y)
        d = np.stack([shapely.distance(pts, ln) for ln in lines], axis=0) / NM
        self.dist_nm = d.min(axis=0).reshape(gx.shape).astype(np.float32)
        self.which = d.argmin(axis=0).reshape(gx.shape).astype(np.int16)

    @classmethod
    @lru_cache(maxsize=1)
    def default(cls) -> "Cables | None":
        try:
            feats = json.loads((ROOT / "taiwan_cables.geojson").read_text(encoding="utf8"))["features"]
        except (OSError, ValueError, KeyError):
            return None
        return cls(feats)

    def _idx(self, lat, lon):
        lat, lon = np.asarray(lat, float), np.asarray(lon, float)
        j = np.clip(np.rint((lon - LON0) / GRID_DEG).astype(int), 0, len(self._lons) - 1)
        i = np.clip(np.rint((lat - LAT0) / GRID_DEG).astype(int), 0, len(self._lats) - 1)
        return i, j

    def distance_nm(self, lat, lon) -> np.ndarray:
        i, j = self._idx(lat, lon)
        return self.dist_nm[i, j]

    def nearest_name(self, lat: float, lon: float) -> str:
        i, j = self._idx(np.array([lat]), np.array([lon]))
        return self.names[int(self.which[i, j][0])]
