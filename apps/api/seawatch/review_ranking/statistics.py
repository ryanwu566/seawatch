"""Transparent empirical-percentile and robust-MAD baselines."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import Phase3BConfig
from .contracts import ScoreFrame, TransformedFeatures


def _aggregate(components: pd.DataFrame, features: TransformedFeatures, config: Phase3BConfig) -> ScoreFrame:
    groups: dict[str, pd.Series] = {}
    for group, names in config.feature_groups.items():
        available = [name for name in names if name in features.feature_names]
        if available:
            groups[group] = components[available].max(axis=1)
    group_frame = pd.DataFrame(groups, index=components.index)
    ordered = np.sort(group_frame.to_numpy(), axis=1)[:, ::-1]
    largest = ordered[:, 0]
    second = ordered[:, 1] if ordered.shape[1] > 1 else np.zeros(len(ordered))
    return ScoreFrame.validate("", pd.Series(100 * (0.7 * largest + 0.3 * second), index=components.index), components)


def score_percentile_baseline(features: TransformedFeatures, config: Phase3BConfig) -> ScoreFrame:
    components = (2.0 * (features.percentiles - 0.5).abs()).clip(0.0, 1.0)
    result = _aggregate(components, features, config)
    return ScoreFrame.validate("empirical_percentile", result.scores, components)


def score_robust_mad_baseline(features: TransformedFeatures, config: Phase3BConfig) -> ScoreFrame:
    components = (1.0 - np.exp(-features.robust_scaled.abs())).clip(0.0, 1.0)
    result = _aggregate(components, features, config)
    return ScoreFrame.validate("robust_mad", result.scores, components)


def ordinary_z_diagnostics(train: pd.DataFrame, later: pd.DataFrame, feature_names: tuple[str, ...]) -> dict[str, object]:
    result: dict[str, object] = {}
    for name in feature_names:
        mean, std = float(train[name].mean()), float(train[name].std(ddof=0))
        result[name] = {"train_mean": mean, "train_std": std, "zero_standard_deviation": std == 0.0, "later_max_abs_z": None if std == 0.0 else float(((later[name] - mean) / std).abs().max())}
    return result
