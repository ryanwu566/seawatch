"""Train on REAL historic AIS (San Francisco Bay), test on the Taiwan simulation.

The two regions share no hand-drawn zones, so only *portable* features are used and
each region learns its own context (traffic baseline, habitual stops, reporting rate)
from its own history. See :data:`features.PORTABLE`.

Training signals available from a real archive without labels:

* Isolation Forest - trained on the unlabeled real windows (mostly normal traffic).
* Gradient boosting - trained on the same real tracks with behaviours *injected*
  (:mod:`inject`), which provides labels while keeping the background genuinely real.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score

from . import history
from .context import DetectionContext, TrafficBaseline
from .features import PORTABLE, window_features
from .inject import inject
from .learned import LearnedContext
from .ml import MLModels, _fit, _vessel_level, build_dataset, make_baseline, make_learned
from .models import Track
from .normalize import RegionNormalizer
from .simulator import normal_traffic


def load_days(paths: list[str | Path], min_fixes: int = 30) -> list[list[Track]]:
    days = []
    for p in paths:
        tr = history.load_tracks(p, min_fixes=min_fixes)
        days.append(tr)
    return days


def _day_bounds(tracks: list[Track]) -> tuple[float, float]:
    t0 = min(float(t.t[0]) for t in tracks)
    start = np.floor(t0 / 86400.0) * 86400.0
    return start, start + 86400.0


def real_frame(tracks: list[Track], baseline: TrafficBaseline, learned: LearnedContext, seed: int | None,
               per_kind: int = 8) -> tuple[pd.DataFrame, list]:
    truth = None
    if seed is not None:
        tracks, truth = inject(tracks, seed, per_kind)
    t0, t1 = _day_bounds(tracks)
    ctx = DetectionContext([], [], baseline)
    df = window_features(tracks, t0, t1, ctx, truth if truth is not None else None, learned)
    if truth is None:
        df["y"] = 0
    df["seed"] = seed if seed is not None else -1
    return df, truth or []


def run_transfer(raw_days: list[list[Track]], sim_train_seeds=range(1, 7), sim_test_seeds=range(31, 39),
                 features: list[str] | None = None, per_kind: int = 8) -> tuple[MLModels, dict[str, Any]]:
    features = features or PORTABLE
    all_tracks = [t for d in raw_days for t in d]
    baseline = TrafficBaseline().fit(all_tracks)
    learned = LearnedContext().fit(all_tracks)
    report: dict[str, Any] = {"features": features,
                              "real_data": {"days": len(raw_days), "vessels": len({t.mmsi for t in all_tracks}),
                                            "reports": int(sum(len(t) for t in all_tracks))}}

    # ---- real training data -------------------------------------------------
    plain, labelled = [], []
    for i, day in enumerate(raw_days[:-1] if len(raw_days) > 1 else raw_days):
        plain.append(real_frame(day, baseline, learned, None)[0])
        labelled.append(real_frame(day, baseline, learned, 100 + i, per_kind)[0])
    unsup = pd.concat(plain, ignore_index=True)
    lab = pd.concat(labelled, ignore_index=True)
    norm_sf = RegionNormalizer(features).fit(unsup)
    models = _fit(norm_sf.transform(lab), features=features, unsup_frame=norm_sf.transform(unsup))
    models.normalizer = norm_sf
    report["real_train"] = {"unlabeled_windows": int(len(unsup)), "labelled_windows": int(len(lab)),
                            "injected_positive_windows": int(lab["y"].sum())}

    # ---- held-out REAL day with injected events ------------------------------
    if len(raw_days) > 1:
        hold, truth = real_frame(raw_days[-1], baseline, learned, 999, per_kind)
        yh = hold["y"].to_numpy()
        hold_n = norm_sf.transform(hold)
        hs_if, hs_gb = models.if_score(hold_n), models.gb_score(hold_n)
        report["real_holdout"] = {
            "windows": int(len(hold)), "positive_windows": int(yh.sum()),
            "isolation_forest": {"roc_auc": round(float(roc_auc_score(yh, hs_if)), 3), "pr_auc": round(float(average_precision_score(yh, hs_if)), 3)},
            "gradient_boosting": {"roc_auc": round(float(roc_auc_score(yh, hs_gb)), 3), "pr_auc": round(float(average_precision_score(yh, hs_gb)), 3)},
            "recall_by_kind": _recall_by_kind(hold, hs_gb, models.thresholds["gb"], truth),
        }

    # ---- Taiwan simulation (never seen in training) ---------------------------
    sim_base = make_baseline(True)
    sim_learned = make_learned(True)
    test, scen = build_dataset(sim_test_seeds, True, sim_base, learned=sim_learned)
    sim_hist = pd.concat([_hist_frame(sd, sim_base, sim_learned) for sd in (101, 102, 103)], ignore_index=True)
    norm_sim = RegionNormalizer(features).fit(sim_hist)
    test_n = norm_sim.transform(test)
    test["if"], test["gb"] = models.if_score(test_n), models.gb_score(test_n)
    y = test["y"].to_numpy()
    methods: dict[str, Any] = {}

    def add(name: str, s: np.ndarray, thr: float):
        methods[name] = {"roc_auc": round(float(roc_auc_score(y, s)), 3), "pr_auc": round(float(average_precision_score(y, s)), 3),
                         **_vessel_level(test, s >= thr, scen)}

    add("Rules (hand-built, Taiwan zones)", test["rules"].to_numpy(), 30.0)
    add("Isolation Forest trained on SF Bay", test["if"].to_numpy(), models.thresholds["if"])
    add("Gradient boosting trained on SF Bay + injected events", test["gb"].to_numpy(), models.thresholds["gb"])
    combo = (test["rules"] >= 30) & ((test["gb"] >= models.thresholds["gb"]) | (test["if"] >= models.thresholds["if"]))
    methods["Rules confirmed by SF-trained ML"] = {"roc_auc": None, "pr_auc": None, **_vessel_level(test, combo.to_numpy(), scen)}

    # in-domain reference: same model class trained on simulation itself
    sim_train, _ = build_dataset(sim_train_seeds, True, sim_base, learned=sim_learned)
    ref = _fit(norm_sim.transform(sim_train), features=features)
    s_ref = ref.gb_score(test_n)
    methods["(reference) Gradient boosting trained on simulation"] = {
        "roc_auc": round(float(roc_auc_score(y, s_ref)), 3), "pr_auc": round(float(average_precision_score(y, s_ref)), 3),
        **_vessel_level(test, s_ref >= 50.0, scen)}
    report["taiwan_sim"] = {"windows": int(len(test)), "positive_windows": int(y.sum()), "methods": methods,
                            "recall_by_kind_gb": _sim_recall_by_kind(test, test["gb"].to_numpy(), models.thresholds["gb"], scen),
                            "recall_by_kind_rules": _sim_recall_by_kind(test, test["rules"].to_numpy(), 30.0, scen)}
    return models, report


def _hist_frame(seed: int, baseline: TrafficBaseline, learned: LearnedContext) -> pd.DataFrame:
    scn = normal_traffic(seed, hard=True)
    return window_features(scn.tracks, scn.t0, scn.t1, DetectionContext(scn.zones, scn.receivers, baseline), None, learned)


def _recall_by_kind(df: pd.DataFrame, score: np.ndarray, thr: float, truth) -> dict[str, str]:
    out: dict[str, list[int]] = {}
    flag = score >= thr
    for t in truth:
        m = df["mmsi"].isin(t.mmsis) & (df["t1"] >= t.t_start - 3600) & (df["t0"] <= t.t_end + 3600)
        hit = bool(flag[m.to_numpy()].any())
        out.setdefault(t.kind, [0, 0])
        out[t.kind][0] += int(hit)
        out[t.kind][1] += 1
    return {k: f"{a}/{b}" for k, (a, b) in out.items()}


def _sim_recall_by_kind(df: pd.DataFrame, score: np.ndarray, thr: float, scen) -> dict[str, str]:
    out: dict[str, list[int]] = {}
    flag = score >= thr
    for scn, _ in scen:
        d = (df["seed"] == scn.seed).to_numpy()
        sub = df[d]
        for t in scn.truth:
            if t.benign:
                continue
            m = sub["mmsi"].isin(t.mmsis) & (sub["t1"] >= t.t_start - 3600) & (sub["t0"] <= t.t_end + 3600)
            hit = bool(flag[d][m.to_numpy()].any())
            out.setdefault(t.kind, [0, 0])
            out[t.kind][0] += int(hit)
            out[t.kind][1] += 1
    return {k: f"{a}/{b}" for k, (a, b) in out.items()}
