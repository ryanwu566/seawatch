"""Explicit rule baseline for behavioral review prioritization."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import Phase3BConfig
from .contracts import ReferenceProfile, ScoreFrame, TransformedFeatures


_TAILS = {
    "sog_median_knots": "low", "sog_p95_knots": "low",
    "low_speed_fraction": "high", "low_speed_duration_seconds": "high",
    "path_distance_m": "low", "displacement_m": "low",
    "path_displacement_ratio": "high", "course_change_abs_sum_deg": "high", "course_change_abs_p95_deg": "high",
}


def score_rule_baseline(features: TransformedFeatures, profile: ReferenceProfile, config: Phase3BConfig) -> ScoreFrame:
    components = pd.DataFrame(0.0, index=features.raw.index, columns=features.feature_names)
    low, high = config.rules.low_quantile, config.rules.high_quantile
    for name in features.feature_names:
        p = features.percentiles[name]
        if _TAILS[name] == "high":
            components[name] = ((p - high) / (1.0 - high)).clip(0.0, 1.0)
        else:
            components[name] = ((low - p) / low).clip(0.0, 1.0)
    groups = []
    for names in config.feature_groups.values():
        active = [name for name in names if name in components]
        if active:
            groups.append(components[active].max(axis=1))
    scores = pd.concat(groups, axis=1).max(axis=1) * 100.0
    return ScoreFrame.validate("rule", scores, components)
