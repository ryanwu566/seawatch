"""Train and evaluate the path-shape model on the supplied April 2026 Taiwan AIS.

    python scripts/train_path_model.py        (needs data/processed/taiwan_ais_apr2026.pkl from build_taiwan_ais.py)

Weak labels: windows in which a vessel announced survey work (towing text / sustained restricted-manoeuvre status).
Evaluation: grouped by vessel, so the model is always scored on vessels it has not seen.
"""
from __future__ import annotations

import pickle
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))
from seawatch.detection import mentorworld, pathml  # noqa: E402

mentorworld._alias()
day, res = pickle.loads(Path("data/processed/taiwan_ais_apr2026.pkl").read_bytes())
by: dict[str, list] = {}
for r in res:
    by.setdefault(r.mmsi, []).append(r)
res_m = [mentorworld._merge(v) for v in by.values()]
day_ids = {t.mmsi for t in day}

print("building windows ...")
ws_day = [w for t in day if t.mmsi not in by for w in pathml.windows_for(t)]
ws_res = [w for t in res_m for w in pathml.windows_for(t)]
ws = ws_day + ws_res

# Confirmed paths override the weak labels: data/labels/confirmed_paths.csv with columns mmsi,t_start,t_end,label,source
# (ISO UTC times; label 1 = confirmed unauthorised / survey activity, 0 = confirmed ordinary). Add real cases here when they exist.
conf = Path("data/labels/confirmed_paths.csv")
if conf.exists():
    import pandas as pd

    c = pd.read_csv(conf, comment="#")
    c["a"] = (pd.to_datetime(c["t_start"], utc=True) - pd.Timestamp(0, tz="UTC")).dt.total_seconds()
    c["b"] = (pd.to_datetime(c["t_end"], utc=True) - pd.Timestamp(0, tz="UTC")).dt.total_seconds()
    n = 0
    for w in ws:
        hit = c[(c["mmsi"].astype(str) == w.mmsi) & (c["a"] <= w.t1) & (c["b"] >= w.t0)]
        if len(hit):
            w.label, w.declared_by, n = int(hit["label"].iloc[0]), "confirmed", n + 1
    print(f"confirmed-path labels applied to {n} windows")
X, y, g = pathml.matrix(ws)
pos_v = sorted({w.mmsi for w in ws if w.label})
print(f"slow windows: {len(ws)} (day file {len(ws_day)}, research files {len(ws_res)}); positives {int(y.sum())} windows on {len(pos_v)} vessels")
names = {t.mmsi: t.name for t in res_m}
for m in pos_v:
    print("   ", m, names.get(m), sum(1 for w in ws if w.mmsi == m and w.label), "windows")

from sklearn.metrics import roc_auc_score  # noqa: E402
from sklearn.model_selection import StratifiedGroupKFold  # noqa: E402

oof = np.zeros(len(y))
cv = StratifiedGroupKFold(n_splits=min(5, len(pos_v)), shuffle=True, random_state=1)
for tr_i, te_i in cv.split(X, y, g):
    oof[te_i] = pathml.score(pathml.fit(X[tr_i], y[tr_i]), X[te_i])
print(f"\nvessel-grouped cross-validated ROC-AUC (path shape only): {roc_auc_score(y, oof):.3f}")

# baseline: the hand-written survey-pattern rule (survey_windows) on the same windows
from seawatch.detection.config import DetectionConfig  # noqa: E402
from seawatch.detection.survey import survey_windows  # noqa: E402

cfg = DetectionConfig.dense()
rule_hit = {}
alltr = {t.mmsi: t for t in list(day) + res_m}
for m in {w.mmsi for w in ws}:
    tr = alltr[m]
    rule_hit[m] = [(tr.t[a], tr.t[b]) for a, b, _ in survey_windows(tr, cfg, lambda a, b: np.zeros(len(a), bool))]
rule = np.array([any(w.t0 <= b and w.t1 >= a for a, b in rule_hit.get(w.mmsi, [])) for w in ws], float)
print(f"hand-written pattern rule: flags {int(rule.sum())} windows; ROC-AUC {roc_auc_score(y, rule):.3f}; "
      f"recall of announced-survey windows {rule[y == 1].mean():.2f}")
for k in (0.005, 0.01, 0.02):
    thr = np.quantile(oof, 1 - k)
    hit = oof >= thr
    print(f"model, flag top {k * 100:.1f}% of slow windows ({int(hit.sum())}): recall of announced-survey windows {hit[y == 1].mean():.2f}, "
          f"vessels with >=1 hit {len({g[i] for i in np.where(hit & (y == 1))[0]})}/{len(pos_v)}")

# what separates them
models = pathml.fit(X, y)
gb = models[0]
imp = sorted(zip(pathml.FEATURES, gb.feature_importances_), key=lambda z: -z[1])[:8]
print("\nmost used shape features:", ", ".join(f"{k} {v:.2f}" for k, v in imp))
print("median feature values, announced-survey windows vs other slow windows:")
for k in ("med_kn", "straightness", "turn_per_nm", "n_legs", "revisit", "axis_share", "dwell", "speed_cv"):
    i = pathml.FEATURES.index(k)
    print(f"   {k:14} survey {np.median(X[y == 1, i]):7.2f}   other {np.median(X[y == 0, i]):7.2f}")

# apply to vessels that announce nothing
cand = [(oof[i], ws[i]) for i in np.argsort(-oof) if ws[i].label == 0][:25]
print("\nhighest-scoring slow windows among vessels that did NOT announce survey work (candidates for review):")
seen = set()
for s, w in cand:
    tr = alltr[w.mmsi]
    print(f"   {s:.2f} {tr.name[:22]:22} {tr.ship_type:8} {w.mmsi} at {w.lat:.2f}N {w.lon:.2f}E  legs {w.feats['n_legs']:.0f} revisit {w.feats['revisit']:.2f} axis {w.feats['axis_share']:.2f} med {w.feats['med_kn']:.1f}kn")

pickle.dump({"windows": [(w.mmsi, w.t0, w.t1, w.lat, w.lon, w.label) for w in ws], "oof": oof}, open("data/processed/_path_scores.pkl", "wb"))
