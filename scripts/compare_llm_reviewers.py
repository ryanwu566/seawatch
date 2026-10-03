"""Compare Featherless-hosted models as path reviewers against the offline rules and the analyst-confirmed examples.

    python scripts/compare_llm_reviewers.py MODEL [MODEL ...]      (key from FEATHERLESS_API in the environment or a .env file)

Sample: every window inside the five confirmed ranges (+-12 h), 15 other flagged windows and 25 unflagged slow windows. Reports, per model: answers
that parsed (no fallback), agreement of the flag with the offline rules, share of confirmed windows flagged, flags raised on unflagged windows, latency.
"""
from __future__ import annotations

import pickle
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))
from seawatch.detection import mentorworld, pathagent  # noqa: E402
from seawatch.detection.cables import Cables  # noqa: E402
from seawatch.detection.llmenv import secret  # noqa: E402
from seawatch.detection.territory import Territory  # noqa: E402

mentorworld._alias()
day, res = pickle.loads(Path("data/processed/taiwan_ais_apr2026.pkl").read_bytes())
by: dict[str, list] = {}
for r in res:
    by.setdefault(r.mmsi, []).append(r)
tracks = [mentorworld._merge(v) for v in by.values()]
alltr = {t.mmsi: t for t in tracks}
terr, cab = Territory.default(), Cables.default()
reviews, _ = pathagent.review_vessels(tracks, pathagent.OfflineReviewer(), terr, cab)
conf = pd.read_csv("data/labels/confirmed_paths.csv", comment="#")
conf["a"] = (pd.to_datetime(conf["t_start"], utc=True) - pd.Timestamp(0, tz="UTC")).dt.total_seconds()
conf["b"] = (pd.to_datetime(conf["t_end"], utc=True) - pd.Timestamp(0, tz="UTC")).dt.total_seconds()
inconf = [r for r in reviews if any(str(c.mmsi) == r.mmsi and c.a <= r.t1 and c.b >= r.t0 for c in conf.itertuples())]
ids = {r.id for r in inconf}
rng = np.random.default_rng(3)
flagged = [r for r in reviews if r.flag and r.id not in ids]
unflagged = [r for r in reviews if not r.flag]
sample = inconf + [flagged[i] for i in rng.choice(len(flagged), min(8, len(flagged)), replace=False)] + \
         [unflagged[i] for i in rng.choice(len(unflagged), min(10, len(unflagged)), replace=False)]
print(f"sample: {len(inconf)} confirmed-range windows, {min(8, len(flagged))} other flagged, {min(10, len(unflagged))} unflagged")

key = secret("FEATHERLESS_API")
for model in sys.argv[1:]:
    rv = pathagent.OpenAICompatReviewer("https://api.featherless.ai/v1", model, key, "featherless", timeout=45.0)
    ok = agree = conf_hit = false_flag = 0
    lat = []
    cats = {}
    for r in sample:
        tr = alltr[r.mmsi]
        i, j = int(np.searchsorted(tr.t, r.t0, "left")), int(np.searchsorted(tr.t, r.t1, "right"))
        rv.path = pathagent.describe_path(tr, i, j)
        t = time.time()
        out = rv.review(r.features, r.context)
        lat.append(time.time() - t)
        parsed = "fallback_reason" not in out
        ok += parsed
        if parsed:
            agree += out["flag"] == r.flag
            conf_hit += (r.id in ids and r.flag and out["flag"])
            false_flag += (not r.flag and out["flag"])
            cats[out["category"]] = cats.get(out["category"], 0) + 1
    n_conf_flagged = sum(1 for r in inconf if r.flag)
    print(f"\n{model}: parsed {ok}/{len(sample)}  agree with rules on flag {agree}/{ok}  confirmed windows kept {conf_hit}/{n_conf_flagged}  "
          f"extra flags on rule-unflagged {false_flag}  median latency {np.median(lat):.1f}s  categories {cats}")
