"""Run the path-analysis agent (offline reviewer, or Claude if ANTHROPIC_API_KEY is set and --claude is given) on the April 2026 data.

    python scripts/evaluate_path_agent.py [--claude] [--images DIR]

Scores it against the analyst-supplied confirmed examples (data/labels/confirmed_paths.csv): of the windows inside a confirmed range,
how many does the agent flag, and what does it call them; and which other vessels it surfaces.
"""
from __future__ import annotations

import argparse
import pickle
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))
from seawatch.detection import mentorworld, pathagent  # noqa: E402
from seawatch.detection.cables import Cables  # noqa: E402
from seawatch.detection.territory import Territory  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--claude", action="store_true")
ap.add_argument("--images", default="")
a = ap.parse_args()

mentorworld._alias()
day, res = pickle.loads(Path("data/processed/taiwan_ais_apr2026.pkl").read_bytes())
by: dict[str, list] = {}
for r in res:
    by.setdefault(r.mmsi, []).append(r)
tracks = [mentorworld._merge(v) for v in by.values()]
day_only = [t for t in day if t.mmsi not in by]
reviewer = pathagent.ClaudeReviewer() if a.claude and pathagent.ClaudeReviewer.available() else pathagent.OfflineReviewer()
print("reviewer:", reviewer.name)
terr, cab = Territory.default(), Cables.default()
reviews, funnel = pathagent.review_vessels(tracks + day_only, reviewer, terr, cab, with_images=bool(a.images))
print("funnel:", funnel)

conf = pd.read_csv("data/labels/confirmed_paths.csv", comment="#")
conf["a"] = (pd.to_datetime(conf["t_start"], utc=True) - pd.Timestamp(0, tz="UTC")).dt.total_seconds()
conf["b"] = (pd.to_datetime(conf["t_end"], utc=True) - pd.Timestamp(0, tz="UTC")).dt.total_seconds()
print("\nconfirmed examples (windows inside the confirmed range):")
hit_v = 0
for _, c in conf.iterrows():
    ws = [r for r in reviews if r.mmsi == str(c["mmsi"]) and r.t0 <= c["b"] and r.t1 >= c["a"]]
    fl = [r for r in ws if r.flag]
    hit_v += bool(fl)
    nm = ws[0].name if ws else str(c["mmsi"])
    print(f"  {nm:22} windows {len(ws):2}  flagged {len(fl):2}  categories {dict(Counter(r.category for r in ws))}")
print(f"vessels with at least one flagged window inside the +-12 h range: {hit_v}/{len(conf)}")
hit36 = 0
for _, c in conf.iterrows():
    ws = [r for r in reviews if r.mmsi == str(c["mmsi"]) and r.flag and r.t0 <= c["b"] + 24 * 3600 and r.t1 >= c["a"] - 24 * 3600]
    hit36 += bool(ws)
print(f"... and within +-36 h (the marked moment is often the fast leg between two working stretches): {hit36}/{len(conf)}")

ids = {str(m) for m in conf["mmsi"]}
others = pathagent.episodes([r for r in reviews if r.mmsi not in ids])
print(f"\nother flagged episodes (not in the confirmed set): {len(others)} on {len({e['mmsi'] for e in others})} vessels")
for e in others[:25]:
    print(f"  {e['name'][:24]:24} {e['category']:24} conf {e['confidence']:.2f} {pd.to_datetime(e['t0'], unit='s').strftime('%m-%d %H:%M')} .. {pd.to_datetime(e['t1'], unit='s').strftime('%m-%d %H:%M')}")
print("\nall categories:", dict(Counter(r.category for r in reviews)))
if a.images:
    Path(a.images).mkdir(parents=True, exist_ok=True)
    alltr = {t.mmsi: t for t in tracks + day_only}
    from seawatch.detection.pathagent import render_png
    for r in [x for x in reviews if x.flag][:40]:
        tr = alltr[r.mmsi]
        i, j = int(np.searchsorted(tr.t, r.t0)), int(np.searchsorted(tr.t, r.t1, "right"))
        (Path(a.images) / f"{r.id}_{r.category}.png").write_bytes(render_png(tr, i, j))
pickle.dump(reviews, open("data/processed/_path_reviews.pkl", "wb"))
