"""San Francisco Bay world: REAL recorded traffic + labelled injected behaviours.

Background traffic is genuine NOAA AIS (public domain). Scripted vessels are added on top,
routed only through water that real vessels were actually seen in (A* over a grid built
from the recorded fixes), so nothing sails across land. Everything added is labelled:

* real vessels altered with :mod:`inject` - dark gap, loitering, spoofed jump, MMSI clone;
* scripted vessels - slow rendezvous, dark ship-to-ship transfer, cluster, restricted-area
  and cable-area entries.

Training uses earlier days (history); the monitored "live" day is held out.
"""

from __future__ import annotations

import heapq
from pathlib import Path

import numpy as np

from .context import TrafficBaseline
from .geo import NM_M, circle_polygon, haversine_m
from .inject import inject
from .learned import LearnedContext, VesselHabits
from .models import Receiver, Scenario, Track, TruthEvent, Zone
from .simulator import KN_MS, Mover, _World

CELL = 0.005  # water-grid resolution (deg, ~0.3 nm)
DATA_GLOB = "data/processed/sfbay_2024-01-0*.parquet"


class WaterGrid:
    """Where vessels have actually been: gives us water, quiet water and routes."""

    def __init__(self, tracks: list[Track], cell: float = CELL):
        self.cell = cell
        la = np.concatenate([t.lat for t in tracks])
        lo = np.concatenate([t.lon for t in tracks])
        self.la0, self.lo0 = float(la.min()) - 0.02, float(lo.min()) - 0.02
        self.ny = int((la.max() - self.la0) / self.cell) + 3
        self.nx = int((lo.max() - self.lo0) / self.cell) + 3
        cnt = np.zeros((self.ny, self.nx), np.int32)
        ij = self.ij(la, lo)
        np.add.at(cnt, (ij[0], ij[1]), 1)
        self.count = cnt
        # a cell is water if it, or a close neighbour, has been used
        k = (cnt > 0).astype(np.int32)
        pad = np.pad(k, 1)
        self.water = (pad[1:-1, 1:-1] + pad[:-2, 1:-1] + pad[2:, 1:-1] + pad[1:-1, :-2] + pad[1:-1, 2:]) > 0

    def ij(self, lat, lon):
        return (np.floor((np.asarray(lat) - self.la0) / self.cell).astype(int), np.floor((np.asarray(lon) - self.lo0) / self.cell).astype(int))

    def xy(self, i: int, j: int) -> tuple[float, float]:
        return self.la0 + (i + 0.5) * self.cell, self.lo0 + (j + 0.5) * self.cell

    def open_water(self, i: int, j: int, r: int = 3) -> bool:
        blk = self.water[max(0, i - r): i + r + 1, max(0, j - r): j + r + 1]
        return blk.size == (2 * r + 1) ** 2 and bool(blk.all())

    def path(self, a: tuple[float, float], b: tuple[float, float], step: int = 4) -> list[tuple[float, float]]:
        """Water-only route a -> b (A* over used cells, preferring busy lanes), thinned to waypoints."""

        (ai,), (aj,) = self.ij([a[0]], [a[1]])
        (bi,), (bj,) = self.ij([b[0]], [b[1]])
        start, goal = (int(ai), int(aj)), (int(bi), int(bj))
        pq = [(0.0, start)]
        came: dict = {start: None}
        g = {start: 0.0}
        while pq:
            _, cur = heapq.heappop(pq)
            if cur == goal:
                break
            for di in (-1, 0, 1):
                for dj in (-1, 0, 1):
                    if di == 0 and dj == 0:
                        continue
                    n = (cur[0] + di, cur[1] + dj)
                    if not (0 <= n[0] < self.ny and 0 <= n[1] < self.nx) or not self.water[n]:
                        continue
                    cost = g[cur] + (1.414 if di and dj else 1.0) * (1.0 + 1.5 / (1.0 + self.count[n] ** 0.5))
                    if cost < g.get(n, 1e18):
                        g[n], came[n] = cost, cur
                        heapq.heappush(pq, (cost + np.hypot(n[0] - goal[0], n[1] - goal[1]), n))
        if goal not in came:
            return [a, b]
        cells, c = [], goal
        while c is not None:
            cells.append(c)
            c = came[c]
        cells.reverse()
        pts = [self.xy(*c) for c in cells[::step]]
        if cells[-1] != cells[::step][-1]:
            pts.append(self.xy(*cells[-1]))
        return [a] + pts[1:-1] + [b] if len(pts) > 2 else [a, b]

    def quiet_spots(self, rng: np.random.Generator, n: int, min_sep_nm: float = 3.0, lo_q: float = 0.05, hi_q: float = 0.75):
        """Open-water spots with modest historic traffic: plausible places for unusual behaviour."""

        used = self.count[self.count > 0]
        lo_c, hi_c = np.quantile(used, [lo_q, hi_q])
        cand = [(i, j) for i, j in zip(*np.where((self.count >= max(2, lo_c)) & (self.count <= hi_c))) if self.open_water(i, j, 2)]
        rng.shuffle(cand)
        spots: list[tuple[float, float]] = []
        for i, j in cand:
            p = self.xy(i, j)
            if all(float(haversine_m(*p, *q)) / NM_M >= min_sep_nm for q in spots):
                spots.append(p)
            if len(spots) == n:
                break
        return spots

    def empty_water_spots(self, tracks: list[Track], rng: np.random.Generator, n: int, min_clear_nm: float = 0.3,
                          max_clear_nm: float = 3.0, min_sep_nm: float = 3.0):
        """Water cells ringed by recorded traffic but with no recorded fix inside ~1 nm: safe places for protected zones."""

        from scipy.spatial import cKDTree

        from .geo import project_xy_m

        la = np.concatenate([t.lat for t in tracks]); lo = np.concatenate([t.lon for t in tracks])
        x, y = project_xy_m(la[::3], lo[::3])
        tree = cKDTree(np.c_[x, y])
        # water enclosed by traffic: recorded fixes in most compass directions around an unused cell
        cand = []
        dirs = [(1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)]
        R = 5
        for i in range(R + 1, self.ny - R - 1):
            for j in range(R + 1, self.nx - R - 1):
                if self.count[i, j] == 0 and sum(self.count[i + di * R, j + dj * R] > 0 for di, dj in dirs) >= 6:
                    cand.append((i, j))
        if not cand:
            return []
        pts = np.array([self.xy(i, j) for i, j in cand])
        cx, cy = project_xy_m(pts[:, 0], pts[:, 1])
        d, _ = tree.query(np.c_[cx, cy])
        ok = [k for k in range(len(cand)) if min_clear_nm * NM_M <= d[k] <= max_clear_nm * NM_M]
        rng.shuffle(ok)
        spots: list[tuple[float, float]] = []
        for k in ok:
            p = (float(pts[k, 0]), float(pts[k, 1]))
            if all(float(haversine_m(*p, *q)) / NM_M >= min_sep_nm for q in spots):
                spots.append(p)
            if len(spots) == n:
                break
        return spots

    def busy_spots(self, rng: np.random.Generator, n: int):
        used = self.count[self.count > 0]
        hi = np.quantile(used, 0.9)
        cand = [(i, j) for i, j in zip(*np.where(self.count >= hi)) if self.open_water(i, j, 2)]
        rng.shuffle(cand)
        return [self.xy(i, j) for i, j in cand[:n]]


def load_days(root: str | Path = ".") -> list[list[Track]]:
    from . import transfer

    files = sorted(Path(root).glob(DATA_GLOB))
    if len(files) < 2:
        raise FileNotFoundError("San Francisco Bay data not found - run scripts/extract_noaa_region.py (see README).")
    return transfer.load_days(files)


def _add_vessel(w: _World, m: Mover, stype: str, flag_hint: str = "US") -> str:
    mmsi, name, flag = w.identity(stype, flag_hint)
    w.add(w.report(m, stype, mmsi, name, flag, force_dense=True))
    return mmsi


def build_sf_scenario(days: list[list[Track]], seed: int = 11, live_index: int = -1) -> tuple[Scenario, dict]:
    """Return (scenario for the live day, context pieces fitted on the history days only)."""

    live = days[live_index]
    hist = [t for k, d in enumerate(days) if k != (live_index % len(days)) for t in d]
    all_tracks = [t for d in days for t in d]
    # the background picture of "normal" (lanes, berths, reporting rate) uses every recorded day BEFORE injection;
    # labelled behaviours are only ever added to the live day afterwards
    baseline = TrafficBaseline().fit(all_tracks)
    learned = LearnedContext().fit(all_tracks)
    la = np.concatenate([t.lat for t in all_tracks]); lo = np.concatenate([t.lon for t in all_tracks])
    bounds = (float(la.min()), float(lo.min()), float(la.max()), float(lo.max()))
    start = float(np.floor(min(t.t[0] for t in live) / 86400.0) * 86400.0)
    t0, t1 = start, start + 86400.0

    grid = WaterGrid(all_tracks)
    rng = np.random.default_rng(seed)
    quiet = grid.quiet_spots(rng, 6)
    busy = grid.busy_spots(rng, 8)
    empty = grid.empty_water_spots(all_tracks, rng, 3)
    if len(empty) < 3:
        empty = (empty + quiet)[:3]
    # --- zones (simulated) placed in quiet open water --------------------------
    zones = [
        Zone("cable-a", "Subsea Cable Protection Area (simulated)", "cable", circle_polygon(*empty[0], 0.22), "No anchoring - protected cable corridor", 1.0),
        Zone("restr-b", "Terminal Security Zone (simulated)", "restricted", circle_polygon(*empty[1], 0.22), "Restricted - authorised vessels only", 0.8),
        Zone("prot-c", "Marine Habitat Protection Area (simulated)", "protected", circle_polygon(*empty[2], 0.22), "Protected habitat", 0.7),
    ]
    w = _World(seed)
    w.t0, w.t1 = t0, t1
    w.zones, w.receivers = zones, []
    w._mmsi_used = {t.mmsi for t in all_tracks}

    def away(p, k):  # a busy start point far from p
        return max(busy, key=lambda b: float(haversine_m(*p, *b)) if b is not busy[k % len(busy)] or True else 0)

    tev = lambda lo_h, hi_h: t0 + rng.uniform(lo_h, hi_h) * 3600  # noqa: E731
    sp = 9.0  # kn

    # 1) slow rendezvous at quiet spot Q3
    P = quiet[3]
    ids = []
    t_arr = tev(8, 16)
    for k, start_pt in enumerate((busy[0], busy[3])):
        route = grid.path(start_pt, P)
        lead = sum(float(haversine_m(*route[i], *route[i + 1])) for i in range(len(route) - 1)) / (sp * KN_MS)
        m = Mover(rng, *route[0], t_arr - lead)
        for pt in route[1:]:
            m.go_to(*pt, sp)
        m.hold(100, 0.5, jitter_nm=0.04)
        t_hold = m.t
        for pt in reversed(route[:-1]):
            m.go_to(*pt, sp)
        ids.append(_add_vessel(w, m, "tanker"))
    w.label("rendezvous", ids, t_hold - 100 * 60, t_hold, "Two tankers meet in open water and drift together")

    # 2) dark ship-to-ship transfer: A transits, goes dark, meets B at quiet spot Q4
    M = quiet[4]
    route = grid.path(busy[1], busy[5])
    mid = route[len(route) // 2]
    t_leave = tev(6, 14)
    a = Mover(rng, *route[0], t_leave - sum(float(haversine_m(*route[i], *route[i + 1])) for i in range(len(route) // 2)) / (sp * KN_MS))
    for pt in route[1:len(route) // 2 + 1]:
        a.go_to(*pt, sp)
    t_dark0 = a.t
    for pt in grid.path(mid, M)[1:]:
        a.go_to(*pt, sp)
    a.hold(90, 0.4)
    t_back = a.t
    for pt in grid.path(M, route[-1])[1:]:
        a.go_to(*pt, sp)
    dark_end = t_back + 25 * 60
    ma, na, fa = w.identity("tanker", "US")
    w.add(w.report(a, "tanker", ma, na, fa, dark=[(t_dark0, dark_end)], force_dense=True))
    b = Mover(rng, M[0] + 0.004, M[1] - 0.004, t_dark0 - 30 * 60)
    b.hold((t_back - t_dark0) / 60 + 60, 0.3, jitter_nm=0.05)
    for pt in grid.path(M, busy[2])[1:]:
        b.go_to(*pt, sp)
    mb = _add_vessel(w, b, "tanker")
    w.label("dark_sts", [ma, mb], t_dark0, dark_end, "Tanker A goes dark, meets slow tanker B in quiet water, resumes")

    # 3) cluster of small vessels at quiet spot Q5 (size / duration / tightness vary with the seed)
    C = quiet[5]
    members = []
    t_c = tev(6, 16)
    n_c = int(rng.integers(4, 8))
    hold_c = float(rng.uniform(45, 120))
    spread = float(rng.uniform(0.004, 0.012))
    for k in range(n_c):
        ang = np.radians(360 / n_c * k + rng.uniform(-10, 10))
        s_pt = (C[0] + 0.03 * np.cos(ang), C[1] + 0.04 * np.sin(ang))
        ij = grid.ij([s_pt[0]], [s_pt[1]])
        route = grid.path(s_pt if grid.water[ij[0][0], ij[1][0]] else busy[k % len(busy)], C)
        lead = sum(float(haversine_m(*route[i], *route[i + 1])) for i in range(len(route) - 1)) / (6 * KN_MS)
        m = Mover(rng, *route[0], t_c - lead)
        for pt in route[1:]:
            m.go_to(pt[0] + rng.normal(0, spread), pt[1] + rng.normal(0, spread), 6)
        m.hold(hold_c, 1.0, jitter_nm=0.1)
        for pt in reversed(route[:-1]):
            m.go_to(*pt, 6)
        members.append(_add_vessel(w, m, "fishing"))
    w.label("cluster", members, t_c, t_c + hold_c * 60 + 600, f"{n_c} small vessels assemble in open water outside any anchorage")

    # benign look-alike: a sailing regatta (pleasure craft milling about for a while) - should NOT alert
    R = quiet[3]
    reg = []
    t_r = tev(8, 16)
    for k in range(int(rng.integers(6, 10))):
        route = grid.path(busy[k % len(busy)], R)
        lead = sum(float(haversine_m(*route[i], *route[i + 1])) for i in range(len(route) - 1)) / (5 * KN_MS)
        m = Mover(rng, *route[0], t_r - lead)
        for pt in route[1:]:
            m.go_to(pt[0] + rng.normal(0, 0.006), pt[1] + rng.normal(0, 0.006), 5)
        m.circle(R[0] + rng.normal(0, 0.004), R[1] + rng.normal(0, 0.004), rng.uniform(0.2, 0.5), rng.uniform(60, 110), 3.0)
        for pt in reversed(route[:-1]):
            m.go_to(*pt, 5)
        reg.append(_add_vessel(w, m, "pleasure"))
    w.label("regatta", reg, t_r, t_r + 110 * 60, "Sailing regatta: many pleasure craft mill about together (benign)", True)

    # 4) zone entries (restricted + cable), one scripted vessel each
    for zid, kind, note, stype, hold_min, start_pt in (
        ("restr-b", "zone_entry", "Unauthorised cargo vessel enters the terminal security zone", "cargo", 20, busy[4]),
        ("cable-a", "zone_entry", "Vessel stops inside the cable protection area (anchoring-like)", "cargo", 70, busy[6]),
    ):
        z = next(z for z in zones if z.id == zid)
        zc = (float(np.mean([p[0] for p in z.polygon])), float(np.mean([p[1] for p in z.polygon])))
        route = grid.path(start_pt, zc)
        t_in = tev(6, 18)
        lead = sum(float(haversine_m(*route[i], *route[i + 1])) for i in range(len(route) - 1)) / (sp * KN_MS)
        m = Mover(rng, *route[0], t_in - lead)
        for pt in route[1:]:
            m.go_to(*pt, sp)
        m.hold(hold_min, 0.4)
        t_out = m.t
        for pt in reversed(route[:-1]):
            m.go_to(*pt, sp)
        mid_ = _add_vessel(w, m, stype)
        w.label(kind, [mid_], t_in - 5 * 60, t_out + 5 * 60, note)

    # real tracks + behaviours injected into real vessels
    real_tracks, real_truth = inject(live, seed, per_kind=4, bounds=bounds,
                                     kinds=["dark_gap", "loitering", "position_jump", "identity_conflict"])
    truth = list(w.truth) + real_truth
    scn = Scenario("San Francisco Bay - real AIS + injected behaviours", t0, t1, real_tracks + w.tracks, zones, [], truth, seed)
    parts = {"baseline": baseline, "learned": learned, "bounds": bounds, "grid": grid, "history": hist}
    return scn, parts


def make_context(scn: Scenario, parts: dict):
    """Detection context for the SF scenario: learned stops/coverage, traffic baseline, zone habits from history."""

    from .config import DetectionConfig
    from .context import DetectionContext
    from .detectors import learn_zone_habits

    ctx = DetectionContext(scn.zones, [], parts["baseline"], learned=parts["learned"], bounds=parts["bounds"])
    ctx.habitual = learn_zone_habits(parts["history"], ctx, DetectionConfig())
    ctx.habits = VesselHabits().fit(parts["history"])
    return ctx
