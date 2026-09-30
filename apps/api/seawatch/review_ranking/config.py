"""Strict Phase 3B configuration loading."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from types import MappingProxyType
from typing import Mapping


@dataclass(frozen=True)
class ReferenceSettings:
    clip_low_quantile: float
    clip_high_quantile: float


@dataclass(frozen=True)
class SupportSettings:
    tier_a_min_fraction: float
    tier_b_min_fraction: float
    tier_b_min_windows: int
    tier_b_min_tracks: int
    tier_b_max_role_gap: float


@dataclass(frozen=True)
class RuleSettings:
    low_quantile: float
    high_quantile: float
    max_reasons: int


@dataclass(frozen=True)
class CalibrationSettings:
    review_budget: int
    budgets: tuple[int, ...]
    bootstrap_replicates: int
    bootstrap_seed: int
    minimum_tracks: int
    maximum_track_share: float
    minimum_jaccard: float
    tie_tolerance: float


@dataclass(frozen=True)
class IsolationForestSettings:
    n_estimators: int
    max_samples: str
    max_features: float
    bootstrap: bool
    contamination: str
    random_state: int
    n_jobs: int


@dataclass(frozen=True)
class Phase3BConfig:
    schema_version: str
    primary_method: str
    split_dates: Mapping[str, str]
    tier_a: tuple[str, ...]
    tier_b: tuple[str, ...]
    tier_c: tuple[str, ...]
    feature_groups: Mapping[str, tuple[str, ...]]
    feature_units: Mapping[str, str]
    reference: ReferenceSettings
    support: SupportSettings
    rules: RuleSettings
    calibration: CalibrationSettings
    isolation_forest: IsolationForestSettings


_TOP = {"schema_version", "primary_method", "split_dates", "tier_a", "tier_b", "tier_c", "feature_groups", "feature_units", "reference", "support", "rules", "calibration", "isolation_forest"}


def phase3b_config_sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_phase3b_config(path: Path) -> Phase3BConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != _TOP:
        raise ValueError("Phase 3B configuration keys do not match the schema")
    tiers = tuple(tuple(raw[name]) for name in ("tier_a", "tier_b", "tier_c"))
    flat = sum(tiers, ())
    if len(flat) != len(set(flat)) or set(flat) != set(raw["feature_units"]):
        raise ValueError("feature tiers must be disjoint and cover configured features")
    grouped = [feature for values in raw["feature_groups"].values() for feature in values]
    if len(grouped) != len(set(grouped)) or not set(grouped).issubset(flat):
        raise ValueError("feature groups must be disjoint and known")
    if raw["schema_version"] != "phase3b-review-ranking-config-v1" or raw["primary_method"] != "empirical_percentile":
        raise ValueError("unsupported Phase 3B configuration")
    reference = ReferenceSettings(**raw["reference"])
    if not 0 <= reference.clip_low_quantile < reference.clip_high_quantile <= 1:
        raise ValueError("invalid clipping quantiles")
    calibration_raw = dict(raw["calibration"])
    calibration_raw["budgets"] = tuple(calibration_raw["budgets"])
    calibration = CalibrationSettings(**calibration_raw)
    if calibration.review_budget <= 0 or any(value <= 0 for value in calibration.budgets):
        raise ValueError("review budgets must be positive")
    return Phase3BConfig(
        schema_version=raw["schema_version"], primary_method=raw["primary_method"], split_dates=MappingProxyType(dict(raw["split_dates"])),
        tier_a=tiers[0], tier_b=tiers[1], tier_c=tiers[2], feature_groups=MappingProxyType({k: tuple(v) for k, v in raw["feature_groups"].items()}),
        feature_units=MappingProxyType(dict(raw["feature_units"])), reference=reference, support=SupportSettings(**raw["support"]),
        rules=RuleSettings(**raw["rules"]), calibration=calibration, isolation_forest=IsolationForestSettings(**raw["isolation_forest"]),
    )
