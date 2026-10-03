"""Region context learned from historic AIS instead of hand-drawn zones.

This is what lets a model trained on one coast (e.g. San Francisco Bay) be applied
to another (Taiwan): the *definitions* are portable - "habitual stopping area",
"normal reporting rate here", "familiar water" - and each region fits them from its
own history.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .models import Track


@dataclass
class LearnedContext:
    cell_deg: float = 0.01
    stop_vessels: dict[tuple[int, int], int] = field(default_factory=dict)
    median_dt: dict[tuple[int, int], float] = field(default_factory=dict)
    global_dt: float = 300.0
    min_stop_vessels: int = 4
    dilate: int = 0
    min_slow_s: float = 1800.0
    max_dt_s: float = 1800.0

    def _cells(self, lat, lon):
        return (np.floor(np.asarray(lat) / self.cell_deg).astype(int), np.floor(np.asarray(lon) / self.cell_deg).astype(int))

    def fit(self, tracks: list[Track]) -> "LearnedContext":
        slow_time: dict[tuple[int, int, str], float] = {}
        dts: dict[tuple[int, int], list[float]] = {}
        all_dt: list[float] = []
        for tr in tracks:
            if len(tr) < 3:
                continue
            ci, cj = self._cells(tr.lat, tr.lon)
            dt = np.diff(tr.t)
            sog = np.nan_to_num(tr.sog, nan=0.0)
            for k in range(len(dt)):
                if dt[k] <= 0:
                    continue
                key = (int(ci[k]), int(cj[k]))
                if dt[k] <= self.max_dt_s:
                    dts.setdefault(key, []).append(float(dt[k]))
                    all_dt.append(float(dt[k]))
                if sog[k] < 1.0 and dt[k] <= self.max_dt_s:
                    sk = (key[0], key[1], tr.mmsi)
                    slow_time[sk] = slow_time.get(sk, 0.0) + float(dt[k])
        per_cell: dict[tuple[int, int], set[str]] = {}
        for (a, b, m), secs in slow_time.items():
            if secs >= self.min_slow_s:
                per_cell.setdefault((a, b), set()).add(m)
        self.stop_vessels = {k: len(v) for k, v in per_cell.items()}
        self.median_dt = {k: float(np.median(v)) for k, v in dts.items() if len(v) >= 5}
        self.global_dt = float(np.median(all_dt)) if all_dt else 300.0
        return self

    def stop_area_frac(self, lat, lon) -> float:
        if not self.stop_vessels or np.size(lat) == 0:
            return 0.0
        ci, cj = self._cells(lat, lon)
        hit = 0
        for a, b in zip(ci.tolist(), cj.tolist()):
            near = sum(self.stop_vessels.get((a + i, b + j), 0) for i in range(-self.dilate, self.dilate + 1) for j in range(-self.dilate, self.dilate + 1))
            hit += near >= self.min_stop_vessels
        return hit / len(ci)

    def stop_mask(self, lat, lon) -> np.ndarray:
        """True where a point lies in (or next to) a habitual stopping area (port, marina, anchorage)."""

        lat, lon = np.atleast_1d(lat), np.atleast_1d(lon)
        out = np.zeros(lat.shape, bool)
        if not self.stop_vessels:
            return out
        ci, cj = self._cells(lat, lon)
        for n, (a, b) in enumerate(zip(ci.tolist(), cj.tolist())):
            out[n] = sum(self.stop_vessels.get((a + i, b + j), 0) for i in range(-self.dilate, self.dilate + 1) for j in range(-self.dilate, self.dilate + 1)) >= self.min_stop_vessels
        return out

    def nearest_stop_nm(self, lat: float, lon: float) -> float:
        """Distance (nm) to the closest habitual stopping area (harbour / marina / anchorage) seen in history."""

        if not self.stop_vessels:
            return 1e9
        if getattr(self, "_stop_xy", None) is None:
            cells = [k for k, v in self.stop_vessels.items() if v >= self.min_stop_vessels]
            self._stop_xy = np.array([((a + 0.5) * self.cell_deg, (b + 0.5) * self.cell_deg) for a, b in cells]) if cells else np.zeros((0, 2))
        if len(self._stop_xy) == 0:
            return 1e9
        from .geo import haversine_nm

        return float(np.min(haversine_nm(lat, lon, self._stop_xy[:, 0], self._stop_xy[:, 1])))

    def covered_mask(self, lat, lon, max_dt: float | None = None) -> np.ndarray:
        """Coverage proxy: cells where vessels historically reported at a steady rate (relative to the feed's own cadence)."""

        if max_dt is None:
            max_dt = max(900.0, 2.0 * self.global_dt)

        ci, cj = self._cells(np.atleast_1d(lat), np.atleast_1d(lon))
        return np.array([self.median_dt.get((a, b), 1e9) <= max_dt for a, b in zip(ci.tolist(), cj.tolist())], bool)

    def expected_interval_s(self, lat: float, lon: float) -> float:
        ci, cj = self._cells(np.array([lat]), np.array([lon]))
        return self.median_dt.get((int(ci[0]), int(cj[0])), self.global_dt)


class VesselHabits:
    """Per-vessel pattern of life: where each vessel has habitually dwelled (slow / stopped) in its own history."""

    def __init__(self, cell_deg: float = 0.02, min_dwell_s: float = 20 * 60, max_dt_s: float = 1800.0):
        self.cell_deg, self.min_dwell_s, self.max_dt_s = cell_deg, min_dwell_s, max_dt_s
        self.cells: dict[str, set[tuple[int, int]]] = {}
        self.gap_p95: dict[str, float] = {}  # each vessel's own 95th-percentile silence between reports (s), from history
        self.gap_n: dict[str, int] = {}
        self.type_gaps: dict[str, np.ndarray] = {}  # silences between reports of vessels of each type (peer distribution)

    def fit(self, tracks: list[Track]) -> "VesselHabits":
        peer: dict[str, list[np.ndarray]] = {}
        for tr in tracks:
            if len(tr) < 3:
                continue
            dt = np.diff(tr.t)
            peer.setdefault(tr.ship_type, []).append(dt)
            if len(dt) >= 15:
                self.gap_p95[tr.mmsi] = float(np.percentile(dt, 95))
                self.gap_n[tr.mmsi] = len(dt)
            slow = (np.nan_to_num(tr.sog, nan=0.0)[:-1] < 1.5) & (dt <= self.max_dt_s)
            ci = np.floor(tr.lat[:-1] / self.cell_deg).astype(int)
            cj = np.floor(tr.lon[:-1] / self.cell_deg).astype(int)
            acc: dict[tuple[int, int], float] = {}
            for a, b, d in zip(ci[slow].tolist(), cj[slow].tolist(), dt[slow].tolist()):
                acc[(a, b)] = acc.get((a, b), 0.0) + d
            keep = {k for k, v in acc.items() if v >= self.min_dwell_s}
            if keep:
                self.cells.setdefault(tr.mmsi, set()).update(keep)
        for k, arrs in peer.items():
            allg = np.concatenate(arrs)
            if len(allg) > 400_000:
                allg = np.random.default_rng(0).choice(allg, 400_000, replace=False)
            self.type_gaps[k] = np.sort(allg)
        return self

    def peer_percentile(self, ship_type: str, gap_s: float) -> float | None:
        """Share of silences by similar vessels that were shorter than ``gap_s`` (None when there are too few peers)."""

        g = self.type_gaps.get(ship_type)
        if g is None or len(g) < 500:
            return None
        return float(np.searchsorted(g, gap_s) / len(g))

    def is_habitual(self, mmsi: str, lat: float, lon: float) -> bool:
        cells = self.cells.get(mmsi)
        if not cells:
            return False
        a, b = int(np.floor(lat / self.cell_deg)), int(np.floor(lon / self.cell_deg))
        return any((a + i, b + j) in cells for i in (-1, 0, 1) for j in (-1, 0, 1))
