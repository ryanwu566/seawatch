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
                if dt[k] <= 1800:
                    dts.setdefault(key, []).append(float(dt[k]))
                    all_dt.append(float(dt[k]))
                if sog[k] < 1.0 and dt[k] <= 1800:
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

    def covered_mask(self, lat, lon, max_dt: float = 900.0) -> np.ndarray:
        """Coverage proxy: cells where vessels historically reported at a steady rate."""

        ci, cj = self._cells(np.atleast_1d(lat), np.atleast_1d(lon))
        return np.array([self.median_dt.get((a, b), 1e9) <= max_dt for a, b in zip(ci.tolist(), cj.tolist())], bool)

    def expected_interval_s(self, lat: float, lon: float) -> float:
        ci, cj = self._cells(np.array([lat]), np.array([lon]))
        return self.median_dt.get((int(ci[0]), int(cj[0])), self.global_dt)
