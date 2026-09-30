from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest


def _config():
    from apps.api.seawatch.trajectories.contracts import load_feature_config

    return load_feature_config(Path("config/trajectory_features_v1.json"))


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "track_id": ["track-a", "track-a", "track-b", "track-a", "track-a"],
            "base_date_time": [
                "2024-01-01T00:20:01Z",
                "2024-01-01T00:00:00Z",
                "2024-01-01T00:05:00Z",
                "2024-01-01T00:10:00Z",
                "2024-01-01T00:00:00Z",
            ],
            "longitude": [-122.37, -122.40, -122.30, -122.38, -122.39],
            "latitude": [37.83, 37.80, 37.75, 37.82, 37.81],
            "sog": [6.0, 3.0, 1.0, 5.0, 4.0],
            "cog": [30.0, 0.0, 90.0, 20.0, 10.0],
            "heading": [30.0, 0.0, 90.0, 20.0, 10.0],
            "vessel_type": [70, 70, 71, 70, 70],
        }
    )


def test_segmentation_uses_strict_greater_than_600_second_boundary() -> None:
    from apps.api.seawatch.trajectories.contracts import validate_observations
    from apps.api.seawatch.trajectories.segmentation import segment_observations

    validated = validate_observations(_frame())
    result = segment_observations(validated.frame, _config())

    track_a = result.observations.loc[result.observations["track_id"].eq("track-a")]
    assert track_a["base_date_time"].is_monotonic_increasing
    assert track_a["segment_id"].tolist() == [
        "track-a:s0001",
        "track-a:s0001",
        "track-a:s0001",
        "track-a:s0002",
    ]
    assert track_a["preceding_gap_seconds"].tolist()[1:] == [0.0, 600.0, 601.0]
    assert result.segments["segment_id"].tolist() == [
        "track-a:s0001",
        "track-a:s0002",
        "track-b:s0001",
    ]


def test_segment_summary_retains_duplicate_time_and_one_point_segments() -> None:
    from apps.api.seawatch.trajectories.contracts import validate_observations
    from apps.api.seawatch.trajectories.segmentation import segment_observations

    result = segment_observations(
        validate_observations(_frame()).frame, _config()
    )
    first = result.segments.set_index("segment_id").loc["track-a:s0001"]
    one_point = result.segments.set_index("segment_id").loc["track-b:s0001"]

    assert len(result.observations) == len(_frame())
    assert first["observation_count"] == 3
    assert first["zero_duration_interval_count"] == 1
    assert first["max_gap_seconds"] == 600.0
    assert first["segment_quality_status"] == "insufficient_duration"
    assert one_point["observation_count"] == 1
    assert one_point["segment_duration_seconds"] == 0.0
    assert one_point["segment_quality_status"] == "insufficient_observations"
    assert (
        result.observations.groupby("segment_id")["track_id"].nunique().max() == 1
    )


def test_segment_summary_marks_inconsistent_vessel_type_without_hiding_it() -> None:
    from apps.api.seawatch.trajectories.contracts import validate_observations
    from apps.api.seawatch.trajectories.segmentation import segment_observations

    frame = _frame()
    frame.loc[frame.index[-1], "vessel_type"] = 72
    result = segment_observations(
        validate_observations(frame).frame, _config()
    )
    first = result.segments.set_index("segment_id").loc["track-a:s0001"]

    assert pd.isna(first["vessel_type"])
    assert not bool(first["vessel_type_consistent"])


def test_segmentation_rejects_negative_gap_after_contract_boundary() -> None:
    from apps.api.seawatch.trajectories.contracts import validate_observations
    from apps.api.seawatch.trajectories.segmentation import segment_observations

    validated = validate_observations(_frame()).frame
    unsorted = validated.iloc[[2, 0, 1, *range(3, len(validated))]].reset_index(
        drop=True
    )

    with pytest.raises(RuntimeError, match="negative"):
        segment_observations(unsorted, _config())
