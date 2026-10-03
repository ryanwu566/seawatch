"""What do the supplied research-vessel AIS files show, and does the threat model recognise it?

    python scripts/analyse_research_vessels.py DAY.csv RESEARCH_01.csv RESEARCH_02.csv
Learns ports / anchorages / normal traffic from the full-day file, then runs the survey-threat model on the research files.
"""
from __future__ import annotations

import pickle
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))
from seawatch.detection import mentor  # noqa: E402
from seawatch.detection.config import DetectionConfig  # noqa: E402
from seawatch.detection.context import DetectionContext, TrafficBaseline  # noqa: E402
from seawatch.detection.declared import assess  # noqa: E402
from seawatch.detection.learned import LearnedContext, VesselHabits  # noqa: E402
from seawatch.detection.survey import survey_windows  # noqa: E402
from seawatch.detection.territory import Territory  # noqa: E402
from seawatch.detection.threat import detect_survey_threat  # noqa: E402


def main(day, r1, r2):
    cache = Path("data/processed/_mentor_cache.pkl")
    if cache.exists():
        day_t, r_t = pickle.loads(cache.read_bytes())
    else:
        day_t, di = mentor.load([day])
        r_t, ri = mentor.load([r1, r2])
        cache.write_bytes(pickle.dumps((day_t, r_t)))
    print("day tracks", len(day_t), "research-file tracks", len(r_t))
    cfg = DetectionConfig()
    terr = Territory.default()
    hist = day_t
    base = TrafficBaseline(cell_deg=0.01).fit(hist, max_dt_s=cfg.densify_max_dt_s)
    learned = LearnedContext(cell_deg=cfg.learn_cell_deg, min_slow_s=cfg.learn_min_slow_s, max_dt_s=cfg.learn_max_dt_s,
                             min_stop_vessels=cfg.learn_min_stop_vessels).fit(hist)
    ctx = DetectionContext([], [], base, learned=learned)
    ctx.territory = terr
    # merge multi-file tracks of the same MMSI
    byid = {}
    for t in r_t:
        byid.setdefault(t.mmsi, []).append(t)
    merged = []
    for m, ts in byid.items():
        t0 = ts[0]
        if len(ts) > 1:
            o = np.argsort(np.concatenate([x.t for x in ts]))
            cat = lambda a: np.concatenate([getattr(x, a) for x in ts])[o]
            from seawatch.detection.models import Track
            t0 = Track(m, t0.name, t0.ship_type, t0.flag, cat("t"), cat("lat"), cat("lon"), cat("sog"), cat("cog"),
                       np.concatenate([x.status for x in ts])[o] if all(x.status is not None for x in ts) else None, t0.imo, t0.extra)
        merged.append(t0)
    print("research vessels", len(merged))
    ev = detect_survey_threat(merged, ctx, cfg)
    byv = {e.mmsis[0]: e for e in ev}
    print(f"{'mmsi':10} {'name':22} {'sub':18} {'fixes':>5} {'TS':>4} {'CZ':>4} {'EEZ':>4} {'V%':>4} {'A':>4} {'pat':>3} rule")
    rows = []
    for t in merged:
        c = terr.code_at(t.lat, t.lon)
        v = np.mean((t.sog >= 5) & (t.sog <= 10))
        a = assess(t).score
        w = survey_windows(t, cfg, ctx.benign_mask)
        e = byv.get(t.mmsi)
        rows.append((len(t), t, int((c == 3).sum()), int((c == 2).sum()), int((c == 1).sum()), v, a, len(w), e.metrics["rule"] if e else ""))
    for n, t, ts, cz, ee, v, a, w, r in sorted(rows, key=lambda x: -x[0])[:60]:
        print(f"{t.mmsi:10} {t.name[:22]:22} {((t.extra or {}).get('subtype') or t.ship_type)[:18]:18} {n:5} {ts:4} {cz:4} {ee:4} {100*v:4.0f} {a:4.2f} {w:3} {r}")
    from collections import Counter
    print(Counter(r[-1] for r in rows))


if __name__ == "__main__":
    main(*sys.argv[1:4])
