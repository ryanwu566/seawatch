"""Per-region ML: learn from a region's own history, test on its held-out live day.

San Francisco Bay: models are trained on the earlier recorded days (real traffic, plus behaviours
injected into real tracks for the supervised model) and evaluated on the held-out day, which also
contains scripted behaviours the models never saw (rendezvous, dark transfer, cluster, zone entry).
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score

from .config import DetectionConfig
from .context import DetectionContext
from .features import PORTABLE, window_features
from .inject import inject
from .ml import MLModels, _fit, _rule_window_scores, _vessel_level, save
from .models import Scenario, Track

INJECT_KINDS = ["dark_gap", "loitering", "position_jump", "identity_conflict"]


def _day_window(tracks: list[Track]) -> tuple[float, float]:
    t0 = float(np.floor(min(t.t[0] for t in tracks) / 86400.0) * 86400.0)
    return t0, t0 + 86400.0


def train_sf(days: list[list[Track]], scn: Scenario, parts: dict, ctx: DetectionContext, seed: int = 11):
    features = PORTABLE
    learned, baseline, bounds = parts["learned"], parts["baseline"], parts["bounds"]
    plain_ctx = DetectionContext([], [], baseline, learned=learned, bounds=bounds)
    plain, lab = [], []
    for i, day in enumerate(days[:-1]):
        t0, t1 = _day_window(day)
        p = window_features(day, t0, t1, plain_ctx, None, learned)
        p["y"] = 0
        plain.append(p)
        tracks, truth = inject(day, 500 + i, 10, bounds, kinds=INJECT_KINDS)
        lab.append(window_features(tracks, t0, t1, plain_ctx, truth, learned))
    unsup = pd.concat(plain, ignore_index=True)
    labelled = pd.concat(lab, ignore_index=True)
    models = _fit(labelled, features=features, unsup_frame=unsup)

    test = window_features(scn.tracks, scn.t0, scn.t1, ctx, scn.truth, learned)
    cfg = DetectionConfig()
    test["rules"], alerts = _rule_window_scores(test, scn, ctx, cfg)
    test["seed"] = scn.seed
    test["if"], test["gb"] = models.if_score(test), models.gb_score(test)
    y = test["y"].to_numpy()
    methods: dict[str, Any] = {}

    def add(name: str, s: np.ndarray, thr: float):
        methods[name] = {"roc_auc": round(float(roc_auc_score(y, s)), 3), "pr_auc": round(float(average_precision_score(y, s)), 3),
                         **_vessel_level(test, s >= thr, [(scn, alerts)])}

    add("Rules", test["rules"].to_numpy(), 30.0)
    add("Isolation Forest (unsupervised)", test["if"].to_numpy(), models.thresholds["if"])
    add("Gradient boosting (supervised)", test["gb"].to_numpy(), models.thresholds["gb"])
    agree = (test["rules"] >= 30) & ((test["gb"] >= models.thresholds["gb"]) | (test["if"] >= models.thresholds["if"]))
    methods["Rules confirmed by ML"] = {"roc_auc": None, "pr_auc": None, **_vessel_level(test, agree.to_numpy(), [(scn, alerts)])}

    # which truth kinds does the supervised model find although it was never shown them?
    seen = set(INJECT_KINDS)
    by_kind: dict[str, dict[str, Any]] = {}
    flag_gb = test["gb"].to_numpy() >= models.thresholds["gb"]
    flag_if = test["if"].to_numpy() >= models.thresholds["if"]
    flag_rules = test["rules"].to_numpy() >= 30
    for t in scn.truth:
        if t.benign:
            continue
        m = (test["mmsi"].isin(t.mmsis) & (test["t1"] >= t.t_start - 3600) & (test["t0"] <= t.t_end + 3600)).to_numpy()
        d = by_kind.setdefault(t.kind, {"n": 0, "rules": 0, "gb": 0, "if": 0, "trained_on": t.kind in seen})
        d["n"] += 1
        d["rules"] += int(flag_rules[m].any())
        d["gb"] += int(flag_gb[m].any())
        d["if"] += int(flag_if[m].any())
    report = {
        "region": "sf-bay", "features": features,
        "train": {"days": len(days) - 1, "unlabeled_windows": int(len(unsup)), "labelled_windows": int(len(labelled)),
                  "injected_windows": int(labelled["y"].sum()), "behaviours_injected": INJECT_KINDS},
        "test": {"windows": int(len(test)), "positive_windows": int(y.sum()), "methods": methods, "by_kind": by_kind},
    }
    return models, report, test


def train_and_save_sf(path: str = "data/models/ml_sf-bay.joblib") -> dict[str, Any]:
    from . import sfworld

    days = sfworld.load_days(".")
    scn, parts = sfworld.build_sf_scenario(days)
    ctx = sfworld.make_context(scn, parts)
    models, report, _ = train_sf(days, scn, parts, ctx)
    save(models, report, path, features=PORTABLE)
    return report
