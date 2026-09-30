"""Deterministic Isolation Forest comparison without classifier labels."""

from __future__ import annotations

import hashlib
import json

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from .config import Phase3BConfig
from .contracts import FittedIsolationForest, ScoreFrame, TransformedFeatures
from .reference import empirical_midrank


def fit_isolation_forest(train: TransformedFeatures, config: Phase3BConfig) -> FittedIsolationForest:
    matrix = train.robust_scaled.loc[:, train.feature_names].to_numpy(dtype=float)
    if not np.isfinite(matrix).all():
        raise ValueError("Isolation Forest input must be finite")
    settings = config.isolation_forest
    params = {
        "n_estimators": settings.n_estimators, "max_samples": settings.max_samples, "max_features": settings.max_features,
        "bootstrap": settings.bootstrap, "contamination": settings.contamination, "random_state": settings.random_state, "n_jobs": settings.n_jobs,
    }
    estimator = IsolationForest(**params).fit(matrix)
    raw = -estimator.score_samples(matrix)
    digest = hashlib.sha256(json.dumps({"parameters": params, "features": train.feature_names}, sort_keys=True).encode()).hexdigest()
    return FittedIsolationForest(estimator, train.feature_names, np.sort(raw), digest)


def score_isolation_forest(model: FittedIsolationForest, features: TransformedFeatures, config: Phase3BConfig) -> ScoreFrame:
    if features.feature_names != model.feature_names:
        raise ValueError("Isolation Forest feature order mismatch")
    matrix = features.robust_scaled.loc[:, features.feature_names].to_numpy(dtype=float)
    if not np.isfinite(matrix).all():
        raise ValueError("Isolation Forest input must be finite")
    raw = -model.estimator.score_samples(matrix)  # type: ignore[attr-defined]
    scores = pd.Series(empirical_midrank(raw, model.train_raw_scores_sorted) * 100.0, index=features.raw.index)
    components = (2.0 * (features.percentiles - 0.5).abs()).clip(0.0, 1.0)
    return ScoreFrame.validate("isolation_forest", scores, components)
