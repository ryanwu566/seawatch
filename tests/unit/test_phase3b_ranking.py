from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from apps.api.seawatch.review_ranking.config import load_phase3b_config
from apps.api.seawatch.review_ranking.contracts import SplitWindows
from apps.api.seawatch.review_ranking.feature_policy import analyze_feature_policy
from apps.api.seawatch.review_ranking.reference import (
    empirical_midrank,
    fit_reference_profile,
    transform_with_reference,
)
from apps.api.seawatch.review_ranking.rules import score_rule_baseline
from apps.api.seawatch.review_ranking.statistics import (
    score_percentile_baseline,
    score_robust_mad_baseline,
)


CONFIG = Path("config/phase3b_review_ranking_v1.json")
CORE = (
    "sog_median_knots",
    "sog_p95_knots",
    "low_speed_fraction",
    "low_speed_duration_seconds",
    "path_distance_m",
    "displacement_m",
)


def _frame(rows: int = 240, tracks: int = 12) -> pd.DataFrame:
    x = np.linspace(0.0, 1.0, rows)
    frame = pd.DataFrame(
        {
            "track_id": [f"t{i % tracks:02}" for i in range(rows)],
            "segment_id": [f"s{i % tracks:02}" for i in range(rows)],
            "window_id": [f"w{i:04}" for i in range(rows)],
            "window_start_utc": pd.date_range("2024-01-01", periods=rows, freq="min", tz="UTC"),
            "window_end_utc": pd.date_range("2024-01-01 00:30", periods=rows, freq="min", tz="UTC"),
            "window_quality_status": "sufficient",
            "sog_median_knots": 2 + 8 * x,
            "sog_p95_knots": 3 + 9 * x,
            "low_speed_fraction": x,
            "low_speed_duration_seconds": 1800 * x,
            "path_distance_m": 100 + 1000 * x,
            "displacement_m": 80 + 800 * x,
            "path_displacement_ratio": np.nan,
            "course_change_abs_sum_deg": np.nan,
            "course_change_abs_p95_deg": np.nan,
            "heading_cog_abs_median_deg": np.nan,
        }
    )
    return frame


def _split(role: str, day: str, frame: pd.DataFrame) -> SplitWindows:
    return SplitWindows(pd.Timestamp(day).date(), role, Path(f"{role}.parquet"), role * 16, frame, 0)


def test_committed_configuration_is_strict_and_immutable() -> None:
    config = load_phase3b_config(CONFIG)
    assert config.schema_version == "phase3b-review-ranking-config-v1"
    assert config.tier_a == CORE
    assert config.primary_method == "empirical_percentile"
    assert config.calibration.review_budget == 20
    assert config.isolation_forest.random_state == 42
    with pytest.raises(Exception):
        config.tier_a += ("x",)  # type: ignore[misc]
    with pytest.raises(TypeError):
        config.split_dates["test"] = "2024-01-04"  # type: ignore[index]


def test_feature_policy_never_accepts_test_and_disables_sparse_tier_b() -> None:
    config = load_phase3b_config(CONFIG)
    train = _split("train", "2024-01-01", _frame())
    calibration_frame = _frame()
    calibration_frame["window_start_utc"] += pd.Timedelta(days=1)
    calibration_frame["window_end_utc"] += pd.Timedelta(days=1)
    calibration = _split("calibration", "2024-01-02", calibration_frame)
    policy = analyze_feature_policy(train, calibration, config)
    assert policy.active_features == CORE
    assert set(policy.disabled_features) >= set(config.tier_b + config.tier_c)
    with pytest.raises(ValueError, match="roles"):
        analyze_feature_policy(train, replace(calibration, split_role="test"), config)


def test_reference_is_train_only_and_midrank_handles_ties() -> None:
    config = load_phase3b_config(CONFIG)
    train = _split("train", "2024-01-01", _frame())
    calibration = _split("calibration", "2024-01-02", _frame())
    policy = analyze_feature_policy(train, calibration, config)
    profile = fit_reference_profile(train, policy, config)
    changed = _frame()
    changed.loc[0, "sog_median_knots"] = 1_000_000
    transformed = transform_with_reference(changed, profile)
    assert profile.features["sog_median_knots"].clip_high < 100
    assert transformed.raw.loc[0, "sog_median_knots"] == 1_000_000
    assert transformed.clipped.loc[0, "sog_median_knots"] == profile.features["sog_median_knots"].clip_high
    assert empirical_midrank(np.array([1.0, 2.0]), np.array([1.0, 1.0, 2.0, 3.0])).tolist() == [0.25, 0.625]
    bad = changed.copy()
    bad.loc[0, "sog_p95_knots"] = np.nan
    with pytest.raises(ValueError, match="missing core"):
        transform_with_reference(bad, profile)


def test_zero_robust_dispersion_stays_empirical_but_is_inactive_for_scaling() -> None:
    config = load_phase3b_config(CONFIG)
    frame = _frame()
    frame["sog_median_knots"] = 0.0
    frame.loc[0, "sog_median_knots"] = 1.0
    train = _split("train", "2024-01-01", frame)
    calibration = _split("calibration", "2024-01-02", frame.copy())
    policy = analyze_feature_policy(train, calibration, config)
    profile = fit_reference_profile(train, policy, config)
    assert profile.features["sog_median_knots"].scale_method == "inactive_zero_dispersion"
    transformed = transform_with_reference(frame, profile)
    assert transformed.robust_scaled["sog_median_knots"].eq(0.0).all()
    assert transformed.percentiles["sog_median_knots"].nunique() == 2


def test_modular_transparent_scorers_are_bounded_and_deterministic() -> None:
    config = load_phase3b_config(CONFIG)
    train = _split("train", "2024-01-01", _frame())
    calibration = _split("calibration", "2024-01-02", _frame())
    policy = analyze_feature_policy(train, calibration, config)
    profile = fit_reference_profile(train, policy, config)
    features = transform_with_reference(_frame(), profile)
    outputs = [
        score_rule_baseline(features, profile, config),
        score_percentile_baseline(features, config),
        score_robust_mad_baseline(features, config),
    ]
    assert [item.method_id for item in outputs] == ["rule", "empirical_percentile", "robust_mad"]
    for item in outputs:
        assert item.scores.between(0, 100).all()
        assert np.isfinite(item.components.to_numpy()).all()
        assert item.scores.equals(type(item).validate(item.method_id, item.scores, item.components).scores)
