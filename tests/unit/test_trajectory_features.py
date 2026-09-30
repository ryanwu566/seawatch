from __future__ import annotations

import math
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest


def _config():
    from apps.api.seawatch.trajectories.contracts import load_feature_config

    return load_feature_config(Path("config/trajectory_features_v1.json"))


def _window_input(
    *,
    longitude: list[float] | None = None,
    latitude: list[float] | None = None,
    sog: list[float | None] | None = None,
    cog: list[float | None] | None = None,
    heading: list[float | None] | None = None,
    offsets_seconds: list[int] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    from apps.api.seawatch.trajectories.windowing import build_feature_windows

    offsets = offsets_seconds or list(range(0, 1801, 180))
    count = len(offsets)
    start = pd.Timestamp("2024-01-01T00:00:00Z")
    timestamps = [start + pd.Timedelta(seconds=value) for value in offsets]
    observations = pd.DataFrame(
        {
            "track_id": ["track-demo"] * count,
            "base_date_time": timestamps,
            "longitude": longitude or [index * 0.001 for index in range(count)],
            "latitude": latitude or [0.0] * count,
            "sog": sog if sog is not None else [5.0] * count,
            "cog": cog if cog is not None else [90.0] * count,
            "heading": heading if heading is not None else [90.0] * count,
            "vessel_type": [70] * count,
            "segment_id": ["track-demo:s0001"] * count,
            "segment_ordinal": [1] * count,
            "preceding_gap_seconds": pd.Series(timestamps).diff().dt.total_seconds(),
        }
    )
    segments = pd.DataFrame(
        {
            "track_id": ["track-demo"],
            "segment_id": ["track-demo:s0001"],
            "segment_ordinal": [1],
            "segment_start_utc": [timestamps[0]],
            "segment_end_utc": [timestamps[-1]],
        }
    )
    return observations, build_feature_windows(observations, segments, _config())


def test_straight_constant_speed_window_has_expected_features() -> None:
    from apps.api.seawatch.trajectories.features import compute_window_features

    observations, windows = _window_input()
    row = compute_window_features(observations, windows, _config()).iloc[0]

    assert row["path_displacement_ratio"] == pytest.approx(1.0, rel=1e-4)
    assert row["course_change_abs_sum_deg"] == pytest.approx(0.0)
    assert row["sog_median_knots"] == pytest.approx(5.0)
    assert row["sog_p95_knots"] == pytest.approx(5.0)
    assert row["heading_cog_abs_median_deg"] == pytest.approx(0.0)


def test_wraparound_course_changes_are_two_degrees_not_358() -> None:
    from apps.api.seawatch.trajectories.features import compute_window_features

    alternating = [359.0 if index % 2 == 0 else 1.0 for index in range(11)]
    observations, windows = _window_input(cog=alternating, heading=alternating)
    row = compute_window_features(observations, windows, _config()).iloc[0]

    assert row["course_change_abs_sum_deg"] == pytest.approx(18.0)
    assert row["course_change_abs_p95_deg"] == pytest.approx(2.0)


def test_stationary_low_speed_window_has_duration_without_fake_ratio() -> None:
    from apps.api.seawatch.trajectories.features import compute_window_features

    observations, windows = _window_input(
        longitude=[0.0] * 11,
        latitude=[0.0] * 11,
        sog=[0.5] * 11,
    )
    row = compute_window_features(observations, windows, _config()).iloc[0]

    assert row["low_speed_fraction"] == pytest.approx(1.0)
    assert row["low_speed_duration_seconds"] == pytest.approx(1620.0)
    assert row["path_distance_m"] == 0.0
    assert row["displacement_m"] == 0.0
    assert pd.isna(row["path_displacement_ratio"])


def test_all_missing_sog_stays_missing_even_when_fraction_threshold_is_zero() -> None:
    from apps.api.seawatch.trajectories.features import compute_window_features

    observations, windows = _window_input(sog=[None] * 11)
    row = compute_window_features(
        observations, windows, replace(_config(), minimum_valid_fraction=0.0)
    ).iloc[0]

    for feature in (
        "sog_median_knots",
        "sog_p95_knots",
        "low_speed_fraction",
        "low_speed_duration_seconds",
    ):
        assert pd.isna(row[feature])


def test_loop_path_is_materially_longer_than_near_zero_displacement() -> None:
    from apps.api.seawatch.trajectories.features import compute_window_features

    longitude = [0.0, 0.001, 0.001, 0.0, 0.0, 0.001, 0.001, 0.0, 0.0, 0.0, 0.0]
    latitude = [0.0, 0.0, 0.001, 0.001, 0.0, 0.0, 0.001, 0.001, 0.0, 0.0, 0.0]
    observations, windows = _window_input(longitude=longitude, latitude=latitude)
    row = compute_window_features(observations, windows, _config()).iloc[0]

    assert row["path_distance_m"] > 800.0
    assert row["displacement_m"] == 0.0
    assert pd.isna(row["path_displacement_ratio"])


def test_missing_angular_inputs_remain_missing_not_zero() -> None:
    from apps.api.seawatch.trajectories.features import compute_window_features

    observations, windows = _window_input(
        cog=[None] * 11,
        heading=[None] * 11,
    )
    row = compute_window_features(observations, windows, _config()).iloc[0]

    assert pd.isna(row["course_change_abs_sum_deg"])
    assert pd.isna(row["course_change_abs_p95_deg"])
    assert pd.isna(row["heading_cog_abs_median_deg"])


def test_near_zero_speed_excludes_course_and_heading_relationship() -> None:
    from apps.api.seawatch.trajectories.features import compute_window_features

    alternating = [359.0 if index % 2 == 0 else 1.0 for index in range(11)]
    observations, windows = _window_input(
        sog=[0.5] * 11,
        cog=alternating,
        heading=alternating,
    )
    row = compute_window_features(observations, windows, _config()).iloc[0]

    assert row["eligible_course_pair_count"] == 0
    assert pd.isna(row["course_change_abs_sum_deg"])
    assert pd.isna(row["heading_cog_abs_median_deg"])


def test_insufficient_window_nulls_all_ten_movement_features() -> None:
    from apps.api.seawatch.trajectories.features import FEATURE_COLUMNS, compute_window_features

    observations, windows = _window_input(
        offsets_seconds=[0, 180, 360, 540, 720, 900, 1080, 1260, 1440, 1800]
    )
    row = compute_window_features(observations, windows, _config()).iloc[0]

    assert row["window_quality_status"] == "insufficient_observations"
    assert row[list(FEATURE_COLUMNS)].isna().all()


def test_duplicate_timestamp_never_produces_nonfinite_feature() -> None:
    from apps.api.seawatch.trajectories.features import FEATURE_COLUMNS, compute_window_features

    observations, windows = _window_input(
        offsets_seconds=[0, 0, 180, 360, 540, 720, 900, 1080, 1260, 1440, 1800]
    )
    result = compute_window_features(observations, windows, _config())

    assert result.iloc[0]["zero_duration_interval_count"] == 1
    assert all(
        pd.isna(value) or math.isfinite(float(value))
        for value in result.loc[0, list(FEATURE_COLUMNS)]
    )


def test_public_feature_schema_is_exact_finite_or_null_and_identifier_safe() -> None:
    from apps.api.seawatch.trajectories.contracts import assert_public_feature_schema
    from apps.api.seawatch.trajectories.features import FEATURE_COLUMNS, compute_window_features
    from apps.api.seawatch.trajectories.windowing import WINDOW_METADATA_COLUMNS

    observations, windows = _window_input()
    result = compute_window_features(observations, windows, _config())

    assert result.columns.tolist() == [*WINDOW_METADATA_COLUMNS, *FEATURE_COLUMNS]
    assert "_observation_positions" not in result
    assert_public_feature_schema(result.columns)
    numeric = result.loc[:, FEATURE_COLUMNS].to_numpy(dtype=float)
    assert (np.isfinite(numeric) | np.isnan(numeric)).all()
