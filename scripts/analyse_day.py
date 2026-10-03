"""Full-day Taiwan AIS + research-vessel AIS from the same days: how much noise, and are the research vessels found?

    python scripts/analyse_day.py   (uses data/processed/_mentor_cache.pkl built by analyse_research_vessels.py)
"""
from __future__ import annotations

import pickle
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))
from seawatch.detection import mentor  # noqa: E402
from seawatch.detection.models import Track  # noqa: E402
from seawatch.detection.threat import factor_table  # noqa: E402

day, res = pickle.loads(Path("data/processed/_mentor_cache.pkl").read_bytes())
t0 = min(float(t.t[0]) for t in day)
t1 = max(float(t.t[-1]) for t in day)
print("day window", time.strftime("%F %H:%M", time.gmtime(t0)), time.strftime("%F %H:%M", time.gmtime(t1)))
by = {t.mmsi: [t] for t in day}
research_ids = set()
for r in res:
    s = mentor._clip(r, t0, t1)
    if s is None:
        continue
    research_ids.add(r.mmsi)
    by.setdefault(r.mmsi, []).append(s)
tracks = []
for m, ts in by.items():
    if len(ts) == 1:
        tracks.append(ts[0])
        continue
    o = np.argsort(np.concatenate([x.t for x in ts]))
    cat = lambda a: np.concatenate([getattr(x, a) for x in ts])[o]
    tracks.append(Track(m, ts[0].name, ts[0].ship_type, ts[0].flag, cat("t"), cat("lat"), cat("lon"), cat("sog"), cat("cog"), None, ts[0].imo,
                        next((x.extra for x in ts if x.extra), None)))
print("tracks", len(tracks), "of which research-file vessels active that day:", len(research_ids))
t = time.time()
r = mentor.analyse(tracks, False, live_frac=0.5)
print("analysed in", round(time.time() - t), "s; history", r["history_vessels"], "live", r["live_vessels"])
print("events", dict(r["events_by_kind"]))
al = r["alerts"]
print("alerts", len(al), "high", sum(a.level == "HIGH" for a in al), "medium", sum(a.level == "MEDIUM" for a in al))
print("discards:")
for (k, why), n in r["discards"]:
    print(f"  {n:>8} {k}: {why}")
ft = factor_table(r["live"], r["ctx"], r["cfg"], r["events"])
print("factors", ft.get("single"))
for c in ft.get("combinations", [])[:8]:
    print("  T%d V%d A%d P%d: %d" % (c["territory"], c["velocity"], c["declared"], c["pattern"], c["vessels"]))
rs = [a for a in al if set(a.mmsis) & research_ids]
print("alerts involving research-file vessels:", len(rs))
for a in sorted(al, key=lambda a: -a.risk)[:25]:
    tag = "R" if set(a.mmsis) & research_ids else " "
    print(f" {tag} {a.risk:5.1f} {a.level:6} {a.title[:100]}")
pickle.dump({"alerts": [(a.risk, a.level, a.title, a.mmsis, a.kinds) for a in al]}, open("data/processed/_day_alerts.pkl", "wb"))
