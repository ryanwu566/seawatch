"""Real-label evaluation on the Taiwan GFW presence data (Sept 2026).

    python scripts/evaluate_gfw_labels.py

Labels: vessels on the OFAC SDN list, matched on IMO / MMSI. They are *designated hulls*, not behaviour. Two questions:

A. Behaviour rules: do designated vessels get higher risk than the rest of the traffic?  (Two untouched 2-day windows,
   with history = all earlier days, so nothing is learned from the window being judged.)
B. Identity screen: can AIS-visible static traits distinguish designated vessels?  Cross-validated twice - random folds
   (optimistic: vessels of one designated fleet leak into both sides) and leave-one-program-out (honest about fleets).
"""

from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.ensemble import HistGradientBoostingClassifier  # noqa: E402
from sklearn.metrics import average_precision_score, roc_auc_score  # noqa: E402
from sklearn.model_selection import StratifiedKFold  # noqa: E402

from seawatch.detection import gfw, labels, twworld  # noqa: E402
from seawatch.detection.alerts import build_alerts  # noqa: E402
from seawatch.detection.config import DetectionConfig  # noqa: E402
from seawatch.detection.detectors import run_all  # noqa: E402
from seawatch.detection.models import Track  # noqa: E402


def auc(pos, neg):
    if not pos or not neg:
        return None
    p, n = np.array(pos), np.array(neg)
    return float(((p[:, None] > n[None, :]).sum() + 0.5 * (p[:, None] == n[None, :]).sum()) / (len(p) * len(n)))


def behaviour_lift(all_tracks: list[Track], ls: labels.LabelSet, window_start: float, days: int = 2) -> dict:
    cfg = DetectionConfig.hourly()
    t1 = window_start + days * 86400.0
    hist = [t.slice(0, int((t.t < window_start).sum())) for t in all_tracks if (t.t < window_start).sum() >= 6]
    live = [t.slice(int((t.t < window_start).sum()), int((t.t < t1).sum())) for t in all_tracks
            if ((t.t >= window_start) & (t.t < t1)).sum() >= 6]
    parts = twworld.contexts(hist, cfg)
    from seawatch.detection.context import DetectionContext

    ctx = DetectionContext(twworld.zones(), [], parts["baseline"], learned=parts["learned"], bounds=twworld.AOI)
    ctx.habits = parts["habits"]
    ev = run_all(live, window_start, t1, ctx, cfg)
    al = build_alerts(ev, live, cfg)
    risk: dict[str, float] = {}
    kinds: dict[str, set] = {}
    for a in al:
        for m in a.mmsis:
            risk[m] = max(risk.get(m, 0.0), a.risk)
            kinds.setdefault(m, set()).update(a.kinds)
    listed = [t for t in live if ls.match(t)]
    lids = {t.mmsi for t in listed}
    pos = [risk.get(t.mmsi, 0.0) for t in listed]
    neg = [risk.get(t.mmsi, 0.0) for t in live if t.mmsi not in lids]
    thr = cfg.alert_min_risk
    return {
        "window_start": window_start, "vessels": len(live), "alerts": len(al), "listed_present": len(listed),
        "listed_flagged": int(sum(r >= thr for r in pos)), "rest_flagged_rate": round(float(np.mean([r >= thr for r in neg])), 4),
        "listed_flagged_rate": round(float(np.mean([r >= thr for r in pos])), 4) if pos else None, "auc": auc(pos, neg),
        "listed_alert_kinds": {t.name: sorted(kinds.get(t.mmsi, [])) for t in listed if risk.get(t.mmsi, 0) >= thr},
    }


def static_table(df: pd.DataFrame) -> pd.DataFrame:
    g = df.groupby("vesselId")
    first = g["t"].min()
    tab = pd.DataFrame({
        "mmsi": g["mmsi"].first(), "imo": g["imo"].first().fillna(""), "name": g["shipName"].first(), "flag": g["flag"].first().fillna("UNK"),
        "vtype": g["vesselType"].first().fillna("NA"), "n_hours": g.size(), "span_h": (g["t"].max() - first) / 3600.0,
        "lat_mean": g["lat"].mean(), "lon_mean": g["lon"].mean(), "lat_std": g["lat"].std().fillna(0), "lon_std": g["lon"].std().fillna(0),
        "n_cells": g.apply(lambda x: len(set(zip(x["lat"].round(1), x["lon"].round(1))))),
    })
    tab["has_imo"] = (tab["imo"].astype(str).str.len() > 0).astype(float)
    tab["fill"] = tab["n_hours"] / np.maximum(tab["span_h"], 1.0)
    tab["mid"] = tab["mmsi"].astype(str).str[:3].astype(int)
    return tab.reset_index()


def design(tab: pd.DataFrame, flags: list[str], types: list[str]) -> pd.DataFrame:
    X = tab[["n_hours", "span_h", "lat_mean", "lon_mean", "lat_std", "lon_std", "n_cells", "fill"]].copy()  # no has_imo: labels are matched on IMO
    for f in flags:
        X[f"flag_{f}"] = (tab["flag"] == f).astype(float)
    for t in types:
        X[f"type_{t}"] = (tab["vtype"] == t).astype(float)
    return X


def screen(tab: pd.DataFrame, y: np.ndarray, groups: np.ndarray) -> dict:
    flags = list(tab["flag"].value_counts().index[:20])
    types = list(tab["vtype"].value_counts().index[:8])
    X = design(tab, flags, types)

    def run(splits):
        oof = {k: np.full(len(y), np.nan) for k in ("flag_type_prior", "profile")}
        for tr, te in splits:
            rate = pd.Series(y[tr]).groupby([tab.iloc[tr]["flag"].to_numpy(), tab.iloc[tr]["vtype"].to_numpy()]).mean()
            key = list(zip(tab.iloc[te]["flag"], tab.iloc[te]["vtype"]))
            oof["flag_type_prior"][te] = [rate.get(k, y[tr].mean()) for k in key]
            m = HistGradientBoostingClassifier(max_depth=3, learning_rate=0.06, max_iter=150, class_weight="balanced", random_state=0)
            m.fit(X.iloc[tr], y[tr])
            oof["profile"][te] = m.predict_proba(X.iloc[te])[:, 1]
        out = {}
        for k, s in oof.items():
            ok = ~np.isnan(s)
            if ok.sum() and y[ok].sum() and (1 - y[ok]).sum():
                out[k] = {"roc_auc": round(float(roc_auc_score(y[ok], s[ok])), 3), "pr_auc": round(float(average_precision_score(y[ok], s[ok])), 3)}
        return out

    rnd = list(StratifiedKFold(5, shuffle=True, random_state=0).split(X, y))
    loo = []
    for g in np.unique(groups[y == 1]):
        te = np.where((groups == g) | ((y == 0) & (np.arange(len(y)) % 5 == hash(str(g)) % 5)))[0]
        tr = np.setdiff1d(np.arange(len(y)), te)
        loo.append((tr, te))
    return {"positives": int(y.sum()), "vessels": int(len(y)), "random_folds": run(rnd), "leave_one_program_out": run(loo)}


def main() -> None:
    files = gfw.daily_files()
    df = gfw.read_presence(files, drop_gear=True)
    ls = labels.LabelSet(labels.load_ofac_sdn("data/labels/ofac_sdn.csv"))
    tracks = gfw.to_tracks(df, min_fixes=6)
    print(f"{len(tracks)} vessels with >=6 hours; listed hulls matched: {sum(bool(ls.match(t)) for t in tracks)}", flush=True)
    day = lambda d: pd.Timestamp(f"2026-09-{d:02d}", tz="UTC").timestamp()  # noqa: E731
    res = {"behaviour": [behaviour_lift(tracks, ls, day(21)), behaviour_lift(tracks, ls, day(28))]}
    for r in res["behaviour"]:
        print(json.dumps(r, default=str), flush=True)

    tab = static_table(df)
    prog = {}
    for lb in ls.labels:
        if lb.kind == "watchlist":
            if lb.imo:
                prog.setdefault(("imo", lb.imo), lb.category)
            if lb.mmsi:
                prog.setdefault(("mmsi", lb.mmsi), lb.category)
    cat = [prog.get(("imo", str(i))) or prog.get(("mmsi", str(m))) or "" for i, m in zip(tab["imo"], tab["mmsi"])]
    y = np.array([1 if c else 0 for c in cat])
    groups = np.array([c.split("-")[0].split("]")[0] if c else "" for c in cat])
    # Labels were matched on IMO, so only vessels that broadcast an IMO can be positive. Compare like with like.
    keep = (tab["has_imo"] > 0).to_numpy()
    res["identity_screen_all_vessels_INFLATED"] = screen(tab, y, groups)
    res["identity_screen"] = screen(tab[keep].reset_index(drop=True), y[keep], groups[keep])
    res["listed_by_program"] = pd.Series([g for g in groups if g]).value_counts().to_dict()
    Path("data/models").mkdir(parents=True, exist_ok=True)
    Path("data/models/gfw_label_eval.json").write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    print(json.dumps(res["identity_screen"], indent=1), res["listed_by_program"])


if __name__ == "__main__":
    main()
