"""Shared spatial context for detectors: zones, receiver coverage, pattern-of-life baseline."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .geo import NM_M, haversine_m, points_in_polygon, polygon_centroid
from .models import Receiver, Track, Zone

SENSITIVE_KINDS = ("protected", "cable", "restricted")
BENIGN_AREA_KINDS = ("port", "anchorage")


@dataclass
class TrafficBaseline:
    """Pattern-of-life model: how many distinct vessels historically used each water cell.

    Learned from historic (event-free) tracks; the route-deviation detector asks
    whether a vessel is in water that normal traffic does not use.
    """

    cell_deg: float = 0.05
    counts: dict[tuple[int, int], int] = field(default_factory=dict)
    n_vessels: int = 0

    def _cells(self, lat: np.ndarray, lon: np.ndarray):
        return np.floor(lat / self.cell_deg).astype(int), np.floor(lon / self.cell_deg).astype(int)

    @staticmethod
    def densify(track: Track, step_nm: float = 1.0):
        """Linear-interpolate a track to roughly ``step_nm`` spacing (for pass-through coverage)."""

        if len(track) < 2:
            return track.t, track.lat, track.lon, track.sog
        d = haversine_m(track.lat[:-1], track.lon[:-1], track.lat[1:], track.lon[1:]) / NM_M
        n_seg = np.clip(np.ceil(d / step_nm).astype(int), 1, 400)
        ts, las, los, sg = [], [], [], []
        for k in range(len(d)):
            f = np.arange(0, n_seg[k]) / n_seg[k]
            ts.append(track.t[k] + f * (track.t[k + 1] - track.t[k]))
            las.append(track.lat[k] + f * (track.lat[k + 1] - track.lat[k]))
            los.append(track.lon[k] + f * (track.lon[k + 1] - track.lon[k]))
            sg.append(np.full(n_seg[k], 0.5 * (track.sog[k] + track.sog[k + 1])))
        ts.append(track.t[-1:]); las.append(track.lat[-1:]); los.append(track.lon[-1:]); sg.append(track.sog[-1:])
        return np.concatenate(ts), np.concatenate(las), np.concatenate(los), np.concatenate(sg)

    def fit(self, tracks: list[Track]) -> "TrafficBaseline":
        per_cell: dict[tuple[int, int], set[str]] = {}
        for tr in tracks:
            _, la, lo, sg = self.densify(tr)
            moving = np.nan_to_num(sg, nan=0.0) >= 3.0
            ci, cj = self._cells(la[moving], lo[moving])
            for key in set(zip(ci.tolist(), cj.tolist())):
                per_cell.setdefault(key, set()).add(tr.mmsi)
        self.counts = {k: len(v) for k, v in per_cell.items()}
        self.n_vessels = len(tracks)
        return self

    def familiarity(self, lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
        """Distinct historic vessels seen in the 3x3 cell neighbourhood."""

        ci, cj = self._cells(np.asarray(lat), np.asarray(lon))
        out = np.zeros(ci.shape, float)
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                out += np.array([self.counts.get((a + di, b + dj), 0) for a, b in zip(ci.tolist(), cj.tolist())], float) / 4.0
        return out


class DetectionContext:
    def __init__(self, zones: list[Zone], receivers: list[Receiver], baseline: TrafficBaseline | None = None,
                 allowlist: set[str] | None = None):
        self.zones = zones
        self.receivers = receivers
        self.baseline = baseline
        self.allowlist = allowlist or set()
        self._bbox = {z.id: (min(p[0] for p in z.polygon), max(p[0] for p in z.polygon),
                             min(p[1] for p in z.polygon), max(p[1] for p in z.polygon)) for z in zones}
        self._centroid = {z.id: polygon_centroid(z.polygon) for z in zones}
        self._radius_nm = {z.id: float(np.mean([haversine_m(*self._centroid[z.id], *p) for p in z.polygon])) / NM_M
                           for z in zones}

    def zone_by_id(self, zid: str) -> Zone:
        return next(z for z in self.zones if z.id == zid)

    def in_zone(self, zone: Zone, lat, lon) -> np.ndarray:
        lat, lon = np.asarray(lat, float), np.asarray(lon, float)
        a, b, c, d = self._bbox[zone.id]
        pre = (lat >= a) & (lat <= b) & (lon >= c) & (lon <= d)
        out = np.zeros(lat.shape, bool)
        if pre.any():
            out[pre] = points_in_polygon(lat[pre], lon[pre], zone.polygon)
        return out

    def in_kinds(self, lat, lon, kinds: tuple[str, ...]) -> np.ndarray:
        out = np.zeros(np.shape(lat), bool)
        for z in self.zones:
            if z.kind in kinds:
                out |= self.in_zone(z, lat, lon)
        return out

    def covered(self, lat, lon) -> np.ndarray:
        d = np.full(np.shape(lat), 1e9)
        for r in self.receivers:
            d = np.minimum(d, haversine_m(lat, lon, r.lat, r.lon) / NM_M / r.range_nm)
        return d <= 1.0

    def nearest_zone(self, lat: float, lon: float, kinds: tuple[str, ...]) -> tuple[Zone | None, float]:
        """Nearest zone of the given kinds and distance (nm) to its edge (0 if inside)."""

        best, best_d = None, 1e9
        for z in self.zones:
            if z.kind not in kinds:
                continue
            c = self._centroid[z.id]
            d = max(0.0, float(haversine_m(lat, lon, *c)) / NM_M - self._radius_nm[z.id])
            if d < best_d:
                best, best_d = z, d
        return best, best_d

    def nearest_port_nm(self, lat: float, lon: float) -> float:
        return self.nearest_zone(lat, lon, ("port",))[1]
