"""Taiwan waters world: REAL Global Fishing Watch vessel-presence data + labelled injected behaviours.

Background: genuine hourly presence of ~8,000 vessels (Sept 2026). The last ``live_days`` days are the monitored "live"
period; everything earlier is history from which the traffic baseline, habitual stopping areas, each vessel's own dwell /
silence habits and each zone's routine visitors are learned. Behaviours of interest are then added and labelled:

* injected into real vessels: dark gap, loitering, spoofed position jump;
* scripted vessels routed through water real vessels use: slow rendezvous, dark ship-to-ship transfer, cluster,
  restricted-area and cable-area entries.

Everything added is coarsened to the feed's own resolution (hourly, ~11 km cells) so detectors face the same data.
Zones are illustrative, not official boundaries.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from . import gfw
from .config import DetectionConfig
from .context import DetectionContext, TrafficBaseline
from .detectors import learn_zone_habits
from .geo import NM_M, circle_polygon, haversine_m
from .inject import inject
from .learned import LearnedContext, VesselHabits
from .models import Scenario, Track, Zone
from .sfworld import WaterGrid
from .simulator import KN_MS, PORTS, Mover, _World

AOI = (21.5, 118.0, 26.5, 123.5)  # min_lat, min_lon, max_lat, max_lon
K = 4.0  # event-time scale relative to minute-level worlds


def _alias_modules() -> None:
    """The cache may have been written when the package was imported as apps.api.seawatch (uvicorn from the repo root)."""

    import sys
    import types

    top = __name__.split(".")[0]
    for stub in ("apps", "apps.api"):
        sys.modules.setdefault(stub, types.ModuleType(stub))
    for name in [n for n in sys.modules if n == top or n.startswith(top + ".")]:
        sys.modules.setdefault("apps.api." + name, sys.modules[name])


def load(live_days: int = 4, min_fixes: int = 6, use_cache: bool = True) -> dict[str, Any]:
    import pickle
    from pathlib import Path

    files = gfw.daily_files()
    cache = Path("data/processed/tw_gfw_cache.pkl")
    if len(files) < live_days + 3:
        if use_cache and cache.exists():  # the SSD is unplugged: run from the processed copy of the same data
            _alias_modules()
            return pickle.loads(cache.read_bytes())["data"]
        raise FileNotFoundError("Taiwan GFW presence data not found - set SEAWATCH_DATA_ROOT (e.g. D:/SeaWatch).")
    key = (live_days, min_fixes, tuple((f.name, f.stat().st_size) for f in files))
    if use_cache and cache.exists():
        try:
            blob = pickle.loads(cache.read_bytes())
            if blob["key"] == key:
                return blob["data"]
        except Exception:  # noqa: BLE001 - a stale cache must never block loading
            pass
    data = _load_uncached(files, live_days, min_fixes)
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(pickle.dumps({"key": key, "data": data}))
    except OSError:
        pass
    return data


def _load_uncached(files, live_days: int, min_fixes: int) -> dict[str, Any]:
    df = gfw.read_presence(files)
    tracks = gfw.to_tracks(df, min_fixes=min_fixes)
    last = float(df["t"].max())
    t_live = float(np.floor(last / 86400.0) * 86400.0 - (live_days - 1) * 86400.0)
    hist, live = [], []
    for tr in tracks:
        m = int((tr.t < t_live).sum())
        if m >= min_fixes:
            hist.append(tr.slice(0, m))
        if len(tr) - m >= min_fixes:
            live.append(tr.slice(m, len(tr)))
    return {"history": hist, "live": live, "t_live": t_live, "t_end": t_live + live_days * 86400.0, "all": tracks}


def zones() -> list[Zone]:
    z = [Zone(f"port-{pid}", f"Port of {pid.title()}", "port", circle_polygon(la, lo, 6.0), "Commercial port approaches", 0.0)
         for pid, (la, lo) in PORTS.items()]
    z += [
        Zone("cable-penghu", "Penghu Subsea Cable Corridor (illustrative)", "cable", circle_polygon(23.95, 119.30, 6.0),
             "Protected submarine cable corridor - no anchoring", 1.0),
        Zone("restr-kinmen", "Kinmen Restricted Waters (illustrative)", "restricted", circle_polygon(24.43, 118.40, 9.0),
             "Restricted waters - transit by authorisation only", 0.8),
    ]
    return z


def contexts(hist: list[Track], cfg: DetectionConfig) -> dict[str, Any]:
    baseline = TrafficBaseline(cell_deg=0.1).fit(hist, max_dt_s=cfg.densify_max_dt_s)
    learned = LearnedContext(cell_deg=cfg.learn_cell_deg, min_slow_s=cfg.learn_min_slow_s, max_dt_s=cfg.learn_max_dt_s,
                             min_stop_vessels=cfg.learn_min_stop_vessels).fit(hist)
    habits = VesselHabits(cell_deg=0.1, min_dwell_s=6 * 3600, max_dt_s=cfg.learn_max_dt_s).fit(hist)
    return {"baseline": baseline, "learned": learned, "habits": habits}


def _add(w: _World, m: Mover, stype: str, flag_hint: str, dark=None) -> str | None:
    mmsi, name, flag = w.identity(stype, flag_hint)
    fine = w.report(m, stype, mmsi, name, flag, dark=dark, force_dense=True)
    coarse = gfw.coarsen(fine)
    if coarse is None:
        return None
    w.tracks.append(coarse)
    return mmsi


def _veto_factory(zs: list[Zone], parts: dict, cfg: DetectionConfig):
    ctx = DetectionContext(zs, [], parts['baseline'], learned=parts['learned'], bounds=AOI)

    def veto(tr: Track, i: int, kind: str = "") -> bool:
        la, lo = float(tr.lat[i]), float(tr.lon[i])
        if kind == "dark_gap" and not bool(ctx.covered(np.array([la]), np.array([lo]))[0]):
            return True  # silence outside the feed's normal coverage is expected, not a finding
        if kind == "position_jump":
            return False
        if bool(ctx.benign_mask(np.array([la]), np.array([lo]))[0]):
            return True  # in / next to a port or habitual stopping area
        if ctx.nearest_zone(la, lo, ("port", "anchorage"))[1] <= 8.0:
            return True
        return bool(parts["habits"].is_habitual(tr.mmsi, la, lo))  # a place this very vessel routinely dwells

    return veto


def build_tw_scenario(data: dict[str, Any], seed: int = 21) -> tuple[Scenario, dict]:
    cfg = DetectionConfig.hourly()
    hist, live, t0, t1 = data["history"], data["live"], data["t_live"], data["t_end"]
    ctxp = contexts(hist, cfg)
    grid = WaterGrid(data["all"], cell=0.1)
    rng = np.random.default_rng(seed)
    quiet = grid.quiet_spots(rng, 6, min_sep_nm=30.0, lo_q=0.1, hi_q=0.7)
    busy = grid.busy_spots(rng, 8)
    if len(quiet) < 6 or len(busy) < 8:
        raise RuntimeError("not enough open water found for scripted events")
    zs = zones()
    w = _World(seed)
    w.t0, w.t1 = t0, t1
    w.zones, w.receivers = zs, []
    w._mmsi_used = {t.mmsi for t in data["all"]}
    tev = lambda lo_h, hi_h: t0 + rng.uniform(lo_h, hi_h) * 3600  # noqa: E731
    sp = 10.0
    flag_hint = lambda: str(rng.choice(["CN", "HK", "PA"]))  # noqa: E731

    def route_time(route, kn):
        return sum(float(haversine_m(*route[i], *route[i + 1])) for i in range(len(route) - 1)) / (kn * KN_MS)

    # 1) slow rendezvous (two tankers) at a quiet spot
    P = quiet[0]
    t_arr = tev(14, 30)
    ids = []
    for k, st in enumerate((busy[0], busy[3])):
        route = grid.path(st, P, step=2)
        m = Mover(rng, *route[0], t_arr - route_time(route, sp))
        for pt in route[1:]:
            m.go_to(*pt, sp)
        m.hold(100 * K, 0.5, jitter_nm=0.3)
        t_hold = m.t
        for pt in reversed(route[:-1]):
            m.go_to(*pt, sp)
        ids.append(_add(w, m, "tanker", flag_hint()))
    ids = [i for i in ids if i]
    w.label("rendezvous", ids, t_hold - 100 * K * 60, t_hold, "Two tankers meet in open water and drift together for hours")

    # 2) dark ship-to-ship transfer
    route = grid.path(busy[1], busy[5], step=2)
    half = max(1, len(route) // 2)
    mid = route[half]
    M = min(quiet[1:], key=lambda q: float(haversine_m(*q, *mid)))  # meeting point close to the route: short detour
    t_leave = tev(12, 26)
    a = Mover(rng, *route[0], t_leave - route_time(route[: half + 1], sp))
    for pt in route[1:half + 1]:
        a.go_to(*pt, sp)
    t_dark0 = a.t
    for pt in grid.path(mid, M, step=2)[1:]:
        a.go_to(*pt, sp)
    a.hold(90 * K, 0.4)
    t_back = a.t
    for pt in grid.path(M, route[-1], step=2)[1:]:
        a.go_to(*pt, sp)
    dark_end = t_back + 60 * 60
    ma, na, fa = w.identity("tanker", flag_hint())
    fine = w.report(a, "tanker", ma, na, fa, dark=[(t_dark0, dark_end)], force_dense=True)
    ca = gfw.coarsen(fine)
    if ca is not None:
        w.tracks.append(ca)
    b = Mover(rng, M[0] + 0.01, M[1] - 0.01, t_dark0 - 2 * 3600)
    b.hold((t_back - t_dark0) / 60 + 4 * 60, 0.3, jitter_nm=0.2)
    for pt in grid.path(M, busy[2], step=2)[1:]:
        b.go_to(*pt, sp)
    mb = _add(w, b, "tanker", flag_hint())
    if ca is not None and mb:
        w.label("dark_sts", [ma, mb], t_dark0, dark_end, "Tanker A goes dark, meets slow tanker B in quiet water, resumes")

    # 3) cluster of small vessels
    C = quiet[2]
    t_c = tev(14, 28)
    n_c = int(rng.integers(6, 10))
    hold_c = float(rng.uniform(60, 110)) * K
    members = []
    for k in range(n_c):
        route = grid.path(busy[k % len(busy)], C, step=2)
        m = Mover(rng, *route[0], t_c - route_time(route, 7))
        for pt in route[1:]:
            m.go_to(pt[0] + rng.normal(0, 0.03), pt[1] + rng.normal(0, 0.03), 7)
        m.hold(hold_c, 1.0, jitter_nm=0.3)
        for pt in reversed(route[:-1]):
            m.go_to(*pt, 7)
        mm = _add(w, m, "fishing", "CN")
        if mm:
            members.append(mm)
    w.label("cluster", members, t_c, t_c + hold_c * 60, f"{len(members)} small vessels assemble in open water outside any port or fishing ground")

    # 4) zone entries
    for zid, note, stype, hold_min, st in (
        ("restr-kinmen", "Unauthorised vessel enters the Kinmen restricted waters", "cargo", 40 * K, busy[4]),
        ("cable-penghu", "Vessel stops inside the Penghu cable corridor (anchoring-like)", "cargo", 70 * K, busy[6]),
    ):
        z = next(z for z in zs if z.id == zid)
        zc = (float(np.mean([p[0] for p in z.polygon])), float(np.mean([p[1] for p in z.polygon])))
        route = grid.path(st, zc, step=2)
        t_in = tev(14, 30)
        m = Mover(rng, *route[0], t_in - route_time(route, sp))
        for pt in route[1:]:
            m.go_to(*pt, sp)
        m.hold(hold_min, 0.4)
        t_out = m.t
        for pt in reversed(route[:-1]):
            m.go_to(*pt, sp)
        mid_ = _add(w, m, stype, flag_hint())
        if mid_:
            w.label("zone_entry", [mid_], t_in - 3600, t_out + 3600, note)

    # behaviours injected into real vessels (hourly-appropriate durations, cell-snapped)
    real, real_truth = inject(live, seed, per_kind=5, bounds=AOI, kinds=["dark_gap", "loitering", "position_jump", "survey_pattern"],
                              time_scale=K, max_dt=7200.0, snap_cell=0.1, min_fixes=20,
                              max_p95_dt=3 * 3600.0, exclude_types=("fishing", "gear"), veto=_veto_factory(zs, ctxp, cfg))
    truth = list(w.truth) + real_truth
    scn = Scenario("Taiwan waters - real AIS presence (GFW) + injected behaviours", t0, t1, real + w.tracks, zs, [], truth, seed)
    parts = {"cfg": cfg, "bounds": AOI, "history": hist, "grid": grid, **ctxp}
    return scn, parts


def make_context(scn: Scenario, parts: dict) -> DetectionContext:
    cfg: DetectionConfig = parts["cfg"]
    ctx = DetectionContext(scn.zones, [], parts["baseline"], learned=parts["learned"], bounds=parts["bounds"])
    ctx.habitual = learn_zone_habits(parts["history"], ctx, cfg)
    ctx.habits = parts["habits"]
    from .territory import Territory

    ctx.territory = Territory.default()
    return ctx
