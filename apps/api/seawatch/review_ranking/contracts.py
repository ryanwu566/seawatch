"""Immutable Phase 3B data contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Mapping

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class SplitWindows:
    source_date: date
    split_role: str
    artifact_path: Path
    artifact_sha256: str
    frame: pd.DataFrame
    rejected_count: int


@dataclass(frozen=True)
class FeaturePolicyAnalysis:
    active_features: tuple[str, ...]
    disabled_features: Mapping[str, str]
    support: Mapping[str, Mapping[str, float | int]]
    policy_hash: str


@dataclass(frozen=True)
class FeatureReference:
    clip_low: float
    clip_high: float
    median: float
    scale: float
    scale_method: str
    reference_sorted: np.ndarray


@dataclass(frozen=True)
class ReferenceProfile:
    feature_names: tuple[str, ...]
    features: Mapping[str, FeatureReference]
    reference_hash: str


@dataclass(frozen=True)
class TransformedFeatures:
    feature_names: tuple[str, ...]
    raw: pd.DataFrame
    clipped: pd.DataFrame
    robust_scaled: pd.DataFrame
    percentiles: pd.DataFrame
    missing: pd.DataFrame


@dataclass(frozen=True)
class ScoreFrame:
    method_id: str
    scores: pd.Series
    components: pd.DataFrame

    @classmethod
    def validate(cls, method_id: str, scores: pd.Series, components: pd.DataFrame) -> "ScoreFrame":
        numeric = pd.to_numeric(scores, errors="coerce").astype(float)
        if len(numeric) != len(components) or not np.isfinite(numeric).all():
            raise ValueError("scores and components must be aligned and finite")
        if not numeric.between(0.0, 100.0).all():
            raise ValueError("review priority scores must be within [0, 100]")
        if not np.isfinite(components.to_numpy(dtype=float)).all():
            raise ValueError("score components must be finite")
        return cls(method_id, numeric.rename("review_priority_score"), components.astype(float))


@dataclass(frozen=True)
class EvidenceReason:
    reason_code: str
    feature_group: str
    feature_name: str
    observed_value: float
    unit: str
    reference_percentile: float
    direction: str
    severity: float
    message: str
    attribution_kind: str


@dataclass(frozen=True)
class FittedIsolationForest:
    estimator: object
    feature_names: tuple[str, ...]
    train_raw_scores_sorted: np.ndarray
    parameter_hash: str


@dataclass(frozen=True)
class BootstrapTrackDraw:
    source_track_id: str
    draw_instance_id: str
    row_indices: tuple[int, ...]
