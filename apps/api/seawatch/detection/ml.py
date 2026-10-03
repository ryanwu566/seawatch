"""Statistical / machine-learning second opinion, benchmarked against the rule detectors.

Two models over the same window features:

* **Isolation Forest** - unsupervised. Needs no labels, so it can be trained on any
  historic AIS archive and answers "does this window look unlike normal traffic?".
* **Gradient-boosted classifier** - supervised. Trained on labelled simulated
  behaviours (or on real tracks with injected events) and answers "does this window
  look like one of the behaviours we care about?".

Both are evaluated on *held-out* scenarios (different random seeds) so the numbers
reflect generalisation, not memorisation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, IsolationForest
from sklearn.metrics import average_precision_score, roc_auc_score

from .alerts import build_alerts
from .config import DetectionConfig
from .context import DetectionContext, TrafficBaseline
from .detectors import run_all
from .features import FEATURES, window_features
from .models import Scenario
from .simulator import build_scenario, normal_traffic, random_plan

# Features whose deviation is shown to the operator, with readable labels/units.
FEATURE_LABEL = {
    "max_gap_min": ("longest silence", "min"), "n_fix": ("AIS reports", ""), "cov_frac": ("receiver coverage", ""),
    "sog_med": ("median speed", "kn"), "sog_p90": ("top speed", "kn"), "low_speed_frac": ("time moving < 2 kn", ""),
    "radius_nm": ("area covered", "nm"), "path_ratio": ("path winding", "x"), "turn_per_h": ("course changes", "deg/h"),
    "max_implied_kn": ("fastest implied jump", "kn"), "n_jump": ("impossible jumps", ""), "fam_mean": ("route familiarity", ""),
    "unfam_frac": ("time in unfamiliar water", ""), "sens_dist_nm": ("distance to protected zone", "nm"),
    "in_sens_frac": ("time inside protected zone", ""), "port_dist_nm": ("distance to port", "nm"),
    "in_benign_frac": ("time in port/anchorage", ""), "in_fish_frac": ("time on fishing ground", ""),
    "slow_nbr_nm": ("nearest slow vessel", "nm"), "group_size": ("vessels within 3 nm", ""),
}


@dataclass
class MLModels:
    iforest: IsolationForest
    gboost: HistGradientBoostingClassifier
    if_ref: np.ndarray  # sorted IF raw scores on training windows (for percentile calibration)
    med: pd.Series
    mad: pd.Series
    features: list[str] = field(default_factory=lambda: list(FEATURES))
    thresholds: dict[str, float] = field(default_factory=dict)
    normalizer: Any = None

    # ---- scoring ---------------------------------------------------------
    def if_score(self, X: pd.DataFrame) -> np.ndarray:
        raw = -self.iforest.score_samples(X[self.features])
        return 100.0 * np.searchsorted(self.if_ref, raw) / len(self.if_ref)

    def gb_score(self, X: pd.DataFrame) -> np.ndarray:
        return self.gboost.predict_proba(X[self.features])[:, 1] * 100.0

    def explain(self, row: pd.Series, top: int = 3) -> list[dict[str, Any]]:
        z = ((row[self.features] - self.med) / self.mad).astype(float)
        out = []
        for name in z.abs().sort_values(ascending=False).index[:top]:
            if name.startswith("is_") or abs(z[name]) < 3:
                continue
            label, unit = FEATURE_LABEL.get(name, (name, ""))
            out.append({"feature": name, "label": label, "value": round(float(row[name]), 2), "unit": unit,
                        "typical": round(float(self.med[name]), 2), "z": round(float(z[name]), 1)})
        return out


def _fit(train: pd.DataFrame, seed: int = 0, features: list[str] | None = None, labels: bool = True,
         unsup_frame: pd.DataFrame | None = None) -> MLModels:
    features = list(features or FEATURES)
    X = (unsup_frame if unsup_frame is not None else train)[features]
    iforest = IsolationForest(n_estimators=300, contamination="auto", random_state=seed, n_jobs=1).fit(X)
    raw = np.sort(-iforest.score_samples(X))
    gb = HistGradientBoostingClassifier(max_depth=4, learning_rate=0.08, max_iter=200, class_weight="balanced",
                                        random_state=seed).fit(train[features], train["y"])
    normal = train.loc[train["y"] == 0, features]
    med = normal.median()
    mad = (normal - med).abs().median().replace(0, np.nan).fillna(normal.std()).replace(0, 1.0) * 1.4826
    m = MLModels(iforest, gb, raw, med, mad, features)
    # operating points from the TRAINING windows only (no peeking at test data)
    ref = unsup_frame if unsup_frame is not None else train.loc[train["y"] == 0]
    m.thresholds["if"] = float(np.percentile(m.if_score(ref), 99.0))
    m.thresholds["gb"] = 50.0
    return m


# --------------------------------------------------------------------------- #
def make_baseline(hard: bool, seeds=(101, 102, 103)) -> TrafficBaseline:
    return TrafficBaseline().fit([t for sd in seeds for t in normal_traffic(sd, hard=hard).tracks])


def scenario_for_seed(seed: int, hard: bool = True) -> Scenario:
    rng = np.random.default_rng(seed)
    return build_scenario(seed, plan=random_plan(rng, 8), hard=hard)


def _rule_window_scores(df: pd.DataFrame, scn: Scenario, ctx: DetectionContext, cfg: DetectionConfig):
    cfg = DetectionConfig.from_dict({**cfg.to_dict(), "alert_min_risk": 1.0})
    events = run_all(scn.tracks, scn.t0, scn.t1, ctx, cfg)
    alerts = build_alerts(events, scn.tracks, cfg)
    score = np.zeros(len(df))
    for a in alerts:
        m = df["mmsi"].isin(a.mmsis) & (df["t1"] >= a.t_start - 3600) & (df["t0"] <= a.t_end + 3600)
        score[m.to_numpy()] = np.maximum(score[m.to_numpy()], a.risk)
    return score, alerts


def make_learned(hard: bool, seeds=(101, 102, 103)):
    from .learned import LearnedContext

    return LearnedContext().fit([t for sd in seeds for t in normal_traffic(sd, hard=hard).tracks])


def build_dataset(seeds, hard: bool, baseline: TrafficBaseline, cfg: DetectionConfig | None = None, learned=None):
    cfg = cfg or DetectionConfig()
    frames, scenarios = [], []
    for sd in seeds:
        scn = scenario_for_seed(sd, hard)
        ctx = DetectionContext(scn.zones, scn.receivers, baseline)
        df = window_features(scn.tracks, scn.t0, scn.t1, ctx, scn.truth, learned)
        df["rules"], alerts = _rule_window_scores(df, scn, ctx, cfg)
        df["seed"] = sd
        frames.append(df)
        scenarios.append((scn, alerts))
    return pd.concat(frames, ignore_index=True), scenarios


def _vessel_level(df: pd.DataFrame, flag: np.ndarray, scenarios, tol: float = 3600.0) -> dict[str, float]:
    tp = fp = 0
    pos = 0
    seeds = {scn.seed: scn for scn, _ in scenarios}
    for sd, g in df.assign(_f=flag).groupby("seed"):
        scn = seeds[sd]
        truth = [t for t in scn.truth if not t.benign]
        pos += len({m for t in truth for m in t.mmsis})
        for mmsi, gg in g[g["_f"]].groupby("mmsi"):
            hit = any(mmsi in t.mmsis and (gg["t1"] >= t.t_start - tol).any() and
                      ((gg["t1"] >= t.t_start - tol) & (gg["t0"] <= t.t_end + tol)).any() for t in truth)
            tp += int(hit)
            fp += int(not hit)
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / pos if pos else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    return {"flagged_vessels": tp + fp, "true": tp, "false": fp, "precision": round(prec, 3), "recall": round(rec, 3), "f1": round(f1, 3)}


def run_benchmark(train_seeds=range(1, 11), test_seeds=range(31, 39), hard: bool = True,
                  features: list[str] | None = None) -> tuple[MLModels, dict[str, Any]]:
    baseline = make_baseline(hard)
    learned = make_learned(hard)
    train, _ = build_dataset(train_seeds, hard, baseline, learned=learned)
    test, scen = build_dataset(test_seeds, hard, baseline, learned=learned)
    models = _fit(train, features=features)
    test["if"] = models.if_score(test)
    test["gb"] = models.gb_score(test)
    test["hybrid"] = np.where(test["rules"] > 0, 0.5 * test["rules"] + 0.5 * test["gb"], 0.35 * test["gb"])
    y = test["y"].to_numpy()
    res: dict[str, Any] = {"train_windows": int(len(train)), "test_windows": int(len(test)),
                           "train_scenarios": len(list(train_seeds)), "test_scenarios": len(list(test_seeds)),
                           "positive_window_rate": round(float(y.mean()), 4), "methods": {}}
    for name, col, thr in (("Rules", "rules", 30.0), ("Isolation Forest (unsupervised)", "if", models.thresholds["if"]),
                           ("Gradient boosting (supervised)", "gb", models.thresholds["gb"]),
                           ("Rules + ML hybrid", "hybrid", 30.0)):
        s = test[col].to_numpy()
        res["methods"][name] = {
            "roc_auc": round(float(roc_auc_score(y, s)), 3), "pr_auc": round(float(average_precision_score(y, s)), 3),
            **_vessel_level(test, s >= thr, scen),
        }
    # rules confirmed by ML: alerts only for vessels where either model also agrees
    agree = (test["rules"] >= 30) & ((test["gb"] >= models.thresholds["gb"]) | (test["if"] >= models.thresholds["if"]))
    res["methods"]["Rules confirmed by ML"] = {"roc_auc": None, "pr_auc": None, **_vessel_level(test, agree.to_numpy(), scen)}
    imp = pd.Series(
        _permutation_importance(models, test), index=models.features).sort_values(ascending=False)
    res["top_features"] = [{"feature": f, "label": FEATURE_LABEL.get(f, (f, ""))[0], "importance": round(float(v), 4)}
                           for f, v in imp.head(8).items()]
    return models, res


def _permutation_importance(models: MLModels, test: pd.DataFrame, n: int = 3) -> np.ndarray:
    rng = np.random.default_rng(0)
    base = average_precision_score(test["y"], models.gb_score(test))
    out = np.zeros(len(models.features))
    for i, f in enumerate(models.features):
        drops = []
        for _ in range(n):
            t2 = test.copy()
            t2[f] = rng.permutation(t2[f].to_numpy())
            drops.append(base - average_precision_score(test["y"], models.gb_score(t2)))
        out[i] = np.mean(drops)
    return out


# --------------------------------------------------------------------------- #
# Persistence + live scoring
# --------------------------------------------------------------------------- #
MODEL_PATH = "data/models/detection_ml.joblib"


def save(models: MLModels, benchmark: dict[str, Any], path: str = MODEL_PATH) -> None:
    import joblib
    from pathlib import Path

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"models": models, "benchmark": benchmark, "features": FEATURES}, path)


def load(path: str = MODEL_PATH) -> tuple[MLModels, dict[str, Any]] | None:
    import joblib
    from pathlib import Path

    if not Path(path).exists():
        return None
    try:
        blob = joblib.load(path)
        if blob.get("features") != FEATURES or blob["models"].features != FEATURES:
            return None  # feature set changed since training
        return blob["models"], blob["benchmark"]
    except Exception:  # noqa: BLE001 - stale/corrupt model must never break the API
        return None


def score_alert(models: MLModels, windows: pd.DataFrame, mmsis: list[str], t_start: float, t_end: float,
                rules_risk: float) -> dict[str, Any]:
    """ML second opinion for one alert: strongest window per model + how it compares with the rules."""

    m = windows[windows["mmsi"].isin(mmsis) & (windows["t1"] >= t_start - 3600) & (windows["t0"] <= t_end + 3600)]
    if m.empty:
        return {"available": False}
    gb, iff = float(m["gb"].max()), float(m["if"].max())
    top = m.loc[m["gb"].idxmax()]
    gb_hit, if_hit = gb >= models.thresholds["gb"], iff >= models.thresholds["if"]
    if gb_hit or if_hit:
        agreement = "agree"
    else:
        agreement = "rules_only"
    return {
        "available": True, "gb_score": round(gb, 1), "if_score": round(iff, 1), "agreement": agreement,
        "gb_flag": gb_hit, "if_flag": if_hit, "deviations": models.explain(top),
        "note": ("Both the rules and the statistical model consider this unusual." if agreement == "agree"
                 else "Only the rule detectors flagged this - the statistical model sees normal behaviour. Lower confidence."),
    }
