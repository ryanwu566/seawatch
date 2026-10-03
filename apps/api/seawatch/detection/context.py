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
    def densify(track: Track, step_nm: float = 1.0, max_dt_s: float = 1800.0, max_kn: float = 50.0):
        """Linear-interpolate a track to roughly ``step_nm`` spacing (for pass-through coverage).

        Only continuously reported, physically plausible legs are interpolated: across a long silence or a
        position jump nobody knows where the vessel went, so those legs contribute their end points only.
        """

        if len(track) < 2:
            return track.t, track.lat, track.lon, track.sog
        d = haversine_m(track.lat[:-1], track.lon[:-1], track.lat[1:], track.lon[1:]) / NM_M
        dt = np.diff(track.t)
        ok = (dt <= max_dt_s) & (d / np.maximum(dt, 1.0) * 3600 <= max_kn)
        n_seg = np.where(ok, np.clip(np.ceil(d / step_nm).astype(int), 1, 400), 1)
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
                 allowlist: set[str] | None = None, learned=None,
                 bounds: tuple[float, float, float, float] | None = None):
        self.habits = None  # VesselHabits: where each vessel routinely dwells (its own pattern of life)
        self.habitual: dict[str, set[str]] = {}  # zone id -> vessels that routinely enter it (learned from history)
        self.bounds = bounds  # (min_lat, min_lon, max_lat, max_lon) of the monitored area, if clipped from a bigger feed
        self.learned = learned  # LearnedContext: stands in for hand-drawn zones/receivers on regions we only know from history
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

    def near_edge(self, lat: float, lon: float, margin_nm: float = 2.0) -> bool:
        """Close to the edge of the monitored area: a vessel there may simply have left or entered the feed."""

        if self.bounds is None:
            return False
        la0, lo0, la1, lo1 = self.bounds
        m_lat = margin_nm / 60.0
        m_lon = margin_nm / 60.0 / max(0.2, float(np.cos(np.radians(lat))))
        return bool(lat < la0 + m_lat or lat > la1 - m_lat or lon < lo0 + m_lon or lon > lo1 - m_lon)

    def benign_mask(self, lat, lon) -> np.ndarray:
        """Ports / anchorages from the zone list OR habitual stopping areas learned from history."""

        m = self.in_kinds(lat, lon, BENIGN_AREA_KINDS)
        if self.learned is not None:
            m = m | self.learned.stop_mask(lat, lon).reshape(np.shape(m))
        return m

    def covered(self, lat, lon) -> np.ndarray:
        if not self.receivers and self.learned is not None:
            return self.learned.covered_mask(lat, lon).reshape(np.shape(lat))
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
        d = self.nearest_zone(lat, lon, ("port",))[1]
        if self.learned is not None:
            d = min(d, self.learned.nearest_stop_nm(lat, lon))
        return d
