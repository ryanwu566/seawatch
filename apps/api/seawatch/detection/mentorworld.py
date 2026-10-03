"""Real Taiwan AIS supplied for the hackathon (April 2026), as two monitored regions.

* ``taiwan-day``      the full-day file (2-3 Apr) plus any research-file vessels active on those days; learned on 2 Apr, monitored 3 Apr.
* ``taiwan-research`` the research-vessel files (1-16 Apr), learned from the full-day file (ports, anchorages), monitored for the whole fortnight.

No behaviour is injected: everything shown is real traffic, and there are no labels, so the assessment reports volumes, not accuracy.
Build the cache once with ``python scripts/build_taiwan_ais.py DAY.csv RESEARCH_01.csv RESEARCH_02.csv``.
"""

from __future__ import annotations

import pickle
from pathlib import Path

import numpy as np

from .config import DetectionConfig
from .context import DetectionContext, TrafficBaseline
from .learned import LearnedContext, VesselHabits
from .models import Scenario, Track
from .territory import Territory

CACHE = Path("data/processed/taiwan_ais_apr2026.pkl")
ZONES = ("taiwan-day", "taiwan-research")


def available() -> bool:
    return CACHE.exists()


def _alias() -> None:
    """Pickles may name the package ``seawatch`` or ``apps.api.seawatch`` depending on how the writer was started: accept both."""

    import sys
    import types

    prefix = "apps.api."
    here = __name__.rsplit(".", 2)[0]  # package this module really lives in
    bare = here[len(prefix):] if here.startswith(prefix) else here
    for stub in ("apps", "apps.api"):
        sys.modules.setdefault(stub, types.ModuleType(stub))
    for name in [n for n in sys.modules if n == here or n.startswith(here + ".")]:
        tail = name[len(here):]
        sys.modules.setdefault(bare + tail, sys.modules[name])
        sys.modules.setdefault(prefix + bare + tail, sys.modules[name])


def _merge(ts: list[Track]) -> Track:
    if len(ts) == 1:
        return ts[0]
    o = np.argsort(np.concatenate([x.t for x in ts]), kind="stable")

    def cat(a):
        return np.concatenate([getattr(x, a) for x in ts])[o]

    extra: dict = {}
    for x in ts:
        extra.update({k: v for k, v in (x.extra or {}).items() if k != "tow_t"})
    tw = [x.extra["tow_t"] for x in ts if x.extra and "tow_t" in x.extra]
    if tw:
        extra["tow_t"] = np.unique(np.concatenate(tw))
    status = np.concatenate([x.status for x in ts])[o] if all(x.status is not None for x in ts) else None
    return Track(ts[0].mmsi, ts[0].name, ts[0].ship_type, ts[0].flag, cat("t"), cat("lat"), cat("lon"), cat("sog"), cat("cog"), status, ts[0].imo, extra or None)


def _clip(tr: Track, a: float, b: float, min_n: int = 4) -> Track | None:
    i, j = int(np.searchsorted(tr.t, a, "left")), int(np.searchsorted(tr.t, b, "right"))
    if j - i < min_n:
        return None
    s = tr.slice(i, j)
    if s.extra and "tow_t" in s.extra:
        tw = s.extra["tow_t"]
        tw = tw[(tw >= a) & (tw <= b)]
        s.extra = {**s.extra, **({"tow_t": tw} if len(tw) else {})}
        if not len(tw):
            s.extra.pop("tow_t", None)
    return s


def load(region: str) -> tuple[Scenario, dict]:
    _alias()
    day, research = pickle.loads(CACHE.read_bytes())
    cfg = DetectionConfig.dense()
    d0 = min(float(t.t[0]) for t in day)
    d1 = max(float(t.t[-1]) for t in day)
    cut = d0 + 0.5 * (d1 - d0)
    if region == "taiwan-day":
        hist = [s for t in day if (s := _clip(t, d0, cut))]
        by: dict[str, list[Track]] = {t.mmsi: [s] for t in day if (s := _clip(t, cut, d1))}
        for r in research:
            if s := _clip(r, cut, d1):
                by.setdefault(r.mmsi, []).append(s)
        tracks = [_merge(v) for v in by.values()]
        t0, t1, name = cut, d1, "Taiwan waters, 3 April 2026 (real AIS)"
    else:
        hist = day
        merged: dict[str, list[Track]] = {}
        for r in research:
            merged.setdefault(r.mmsi, []).append(r)
        tracks = [_merge(v) for v in merged.values()]
        t0 = min(float(t.t[0]) for t in tracks)
        t1 = max(float(t.t[-1]) for t in tracks)
        name = "Research-type vessels near Taiwan, 1-16 April 2026 (real AIS)"
    baseline = TrafficBaseline(cell_deg=0.01).fit(hist, max_dt_s=cfg.densify_max_dt_s)
    learned = LearnedContext(cell_deg=cfg.learn_cell_deg, min_slow_s=cfg.learn_min_slow_s, max_dt_s=cfg.learn_max_dt_s,
                             min_stop_vessels=cfg.learn_min_stop_vessels).fit(hist)
    habits = VesselHabits(cell_deg=0.01, min_dwell_s=6 * 3600, max_dt_s=cfg.learn_max_dt_s).fit(hist)
    la = np.concatenate([t.lat for t in tracks])
    lo = np.concatenate([t.lon for t in tracks])
    bounds = (float(la.min()), float(lo.min()), float(la.max()), float(lo.max()))
    scn = Scenario(name, float(t0), float(t1), tracks, [], [], [])
    parts = {"baseline": baseline, "learned": learned, "habits": habits, "bounds": bounds, "cfg": cfg, "history": hist}
    return scn, parts


def make_context(scn: Scenario, parts: dict) -> DetectionContext:
    ctx = DetectionContext(scn.zones, [], parts["baseline"], learned=parts["learned"], bounds=parts["bounds"])
    ctx.habits = parts["habits"]
    ctx.territory = Territory.default()
    return ctx
