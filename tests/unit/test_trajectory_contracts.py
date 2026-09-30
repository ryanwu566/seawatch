from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest


CONFIG_PATH = Path("config/trajectory_features_v1.json")


def test_committed_feature_config_loads_approved_engineering_defaults() -> None:
    from apps.api.seawatch.trajectories.contracts import load_feature_config

    config = load_feature_config(CONFIG_PATH)

    assert config.segment_gap_seconds == 600.0
    assert config.window_duration_seconds == 1800.0
    assert config.window_stride_seconds == 300.0
    assert config.minimum_window_observations == 10
    assert config.minimum_observed_span_seconds == 1200.0
    assert config.minimum_valid_fraction == 0.80
    assert config.low_speed_threshold_knots == 3.0
    assert config.course_min_speed_knots == 1.0
    assert config.minimum_displacement_for_ratio_m == 50.0


@pytest.mark.parametrize(
    ("setting", "value"),
    [
        ("segment_gap_seconds", 0),
        ("window_duration_seconds", 0),
        ("window_stride_seconds", 0),
        ("minimum_window_observations", 0),
        ("minimum_observed_span_seconds", -1),
        ("minimum_valid_fraction", 1.01),
        ("low_speed_threshold_knots", -0.1),
        ("course_min_speed_knots", -0.1),
        ("minimum_displacement_for_ratio_m", -0.1),
    ],
)
def test_feature_config_rejects_invalid_setting_by_name(
    tmp_path: Path, setting: str, value: float
) -> None:
    from apps.api.seawatch.trajectories.contracts import load_feature_config

    payload = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    payload[setting] = value
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match=setting):
        load_feature_config(path)


def test_feature_config_rejects_stride_longer_than_duration(tmp_path: Path) -> None:
    from apps.api.seawatch.trajectories.contracts import load_feature_config

    payload = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    payload["window_stride_seconds"] = payload["window_duration_seconds"] + 1
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="window_stride_seconds"):
        load_feature_config(path)


def test_feature_config_rejects_unknown_keys(tmp_path: Path) -> None:
    from apps.api.seawatch.trajectories.contracts import load_feature_config

    payload = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    payload["window_duraton_seconds"] = payload["window_duration_seconds"]
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="window_duraton_seconds"):
        load_feature_config(path)


def _observation_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "track_id": ["track-a", "track-a", "track-b"],
            "base_date_time": [
                "2024-01-01T00:01:00Z",
                "2024-01-01T00:00:00Z",
                "2024-01-01T00:02:00Z",
            ],
            "longitude": [-122.39, -122.40, -122.38],
            "latitude": [37.81, 37.80, 37.82],
            "sog": [5.0, -1.0, None],
            "cog": [90.0, 361.0, None],
            "heading": [90.0, 511.0, None],
            "vessel_type": [70, 70, 71],
        }
    )


def test_validation_sorts_utc_and_normalizes_semantically_invalid_navigation() -> None:
    from apps.api.seawatch.trajectories.contracts import (
        PHASE1_COLUMNS,
        validate_observations,
    )

    result = validate_observations(_observation_frame())

    assert result.frame.columns.tolist() == list(PHASE1_COLUMNS)
    assert result.frame.groupby("track_id")["base_date_time"].apply(
        lambda values: values.is_monotonic_increasing
    ).all()
    assert str(result.frame["base_date_time"].dtype).endswith("UTC]")
    assert result.stats.input_out_of_order_pairs == 1
    normalized = result.frame.loc[result.frame["longitude"].eq(-122.40)].iloc[0]
    assert pd.isna(normalized["sog"])
    assert pd.isna(normalized["cog"])
    assert pd.isna(normalized["heading"])
    assert result.stats.invalid_sog_rows == 1
    assert result.stats.invalid_cog_rows == 1
    assert result.stats.invalid_heading_rows == 1


@pytest.mark.parametrize(
    ("column", "value", "message"),
    [
        ("base_date_time", None, "base_date_time"),
        ("longitude", None, "coordinates"),
        ("longitude", 181.0, "coordinates"),
        ("latitude", -91.0, "coordinates"),
        ("track_id", "   ", "track_id"),
    ],
)
def test_validation_rejects_invalid_required_observation_values(
    column: str, value: object, message: str
) -> None:
    from apps.api.seawatch.trajectories.contracts import validate_observations

    frame = _observation_frame()
    frame.loc[0, column] = value

    with pytest.raises(ValueError, match=message):
        validate_observations(frame)


def test_validation_rejects_missing_required_column() -> None:
    from apps.api.seawatch.trajectories.contracts import validate_observations

    with pytest.raises(ValueError, match="heading"):
        validate_observations(_observation_frame().drop(columns="heading"))


def test_validation_rejects_nullable_float_coordinate_missing_value() -> None:
    from apps.api.seawatch.trajectories.contracts import validate_observations

    frame = _observation_frame()
    frame["longitude"] = frame["longitude"].astype("Float64")
    frame.loc[0, "longitude"] = pd.NA

    with pytest.raises(ValueError, match="coordinates"):
        validate_observations(frame)


@pytest.mark.parametrize(
    "forbidden",
    ["mmsi", "VeSsEl_NaMe", "IMO", "call_SIGN", "SOURCE_VESSEL_ID", "source_id"],
)
def test_privacy_guard_rejects_every_direct_identifier(forbidden: str) -> None:
    from apps.api.seawatch.trajectories.contracts import assert_public_feature_schema

    with pytest.raises(ValueError, match="forbidden"):
        assert_public_feature_schema(["track_id", forbidden, "path_distance_m"])
