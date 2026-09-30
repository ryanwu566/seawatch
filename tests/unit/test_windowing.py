from __future__ import annotations

from pathlib import Path

import pandas as pd


def _config():
    from apps.api.seawatch.trajectories.contracts import load_feature_config

    return load_feature_config(Path("config/trajectory_features_v1.json"))


def _segment(
    timestamps: list[pd.Timestamp],
    *,
    track_id: str = "track-a",
    segment_ordinal: int = 1,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    segment_id = f"{track_id}:s{segment_ordinal:04d}"
    observations = pd.DataFrame(
        {
            "track_id": track_id,
            "base_date_time": timestamps,
            "longitude": [-122.4 + index * 0.001 for index in range(len(timestamps))],
            "latitude": [37.8] * len(timestamps),
            "sog": [5.0] * len(timestamps),
            "cog": [90.0] * len(timestamps),
            "heading": [90.0] * len(timestamps),
            "vessel_type": [70] * len(timestamps),
            "segment_id": segment_id,
            "segment_ordinal": segment_ordinal,
            "preceding_gap_seconds": pd.Series(timestamps).diff().dt.total_seconds(),
        }
    )
    segments = pd.DataFrame(
        {
            "track_id": [track_id],
            "segment_id": [segment_id],
            "segment_ordinal": [segment_ordinal],
            "segment_start_utc": [timestamps[0]],
            "segment_end_utc": [timestamps[-1]],
        }
    )
    return observations, segments


def test_windows_are_segment_anchored_full_duration_and_half_open() -> None:
    from apps.api.seawatch.trajectories.windowing import build_feature_windows

    timestamps = list(
        pd.date_range("2024-01-01T00:02:00Z", "2024-01-01T01:02:00Z", freq="5min")
    )
    observations, segments = _segment(timestamps)

    windows = build_feature_windows(observations, segments, _config())

    assert windows["window_start_utc"].tolist() == list(
        pd.date_range("2024-01-01T00:02:00Z", "2024-01-01T00:32:00Z", freq="5min")
    )
    assert (
        windows["window_end_utc"] - windows["window_start_utc"]
    ).dt.total_seconds().eq(1800.0).all()
    first_positions = windows.iloc[0]["_observation_positions"]
    second_positions = windows.iloc[1]["_observation_positions"]
    first_times = observations.iloc[list(first_positions)]["base_date_time"].tolist()
    second_times = observations.iloc[list(second_positions)]["base_date_time"].tolist()
    assert pd.Timestamp("2024-01-01T00:32:00Z") not in first_times
    assert pd.Timestamp("2024-01-01T00:32:00Z") in second_times
    assert len(first_positions) == len(set(first_positions))


def test_windows_remain_inside_their_track_and_segment() -> None:
    from apps.api.seawatch.trajectories.windowing import build_feature_windows

    first_obs, first_segments = _segment(
        list(pd.date_range("2024-01-01T00:00:00Z", periods=8, freq="5min"))
    )
    second_obs, second_segments = _segment(
        list(pd.date_range("2024-01-01T01:00:01Z", periods=8, freq="5min")),
        segment_ordinal=2,
    )
    third_obs, third_segments = _segment(
        list(pd.date_range("2024-01-01T00:00:00Z", periods=8, freq="5min")),
        track_id="track-b",
    )
    observations = pd.concat([first_obs, second_obs, third_obs], ignore_index=True)
    segments = pd.concat(
        [first_segments, second_segments, third_segments], ignore_index=True
    )

    windows = build_feature_windows(observations, segments, _config())

    for _, row in windows.iterrows():
        members = observations.iloc[list(row["_observation_positions"])]
        assert members["track_id"].unique().tolist() == [row["track_id"]]
        assert members["segment_id"].unique().tolist() == [row["segment_id"]]


def test_short_segment_produces_no_full_window() -> None:
    from apps.api.seawatch.trajectories.windowing import build_feature_windows

    observations, segments = _segment(
        [
            pd.Timestamp("2024-01-01T00:00:00Z"),
            pd.Timestamp("2024-01-01T00:17:30Z"),
        ]
    )

    assert build_feature_windows(observations, segments, _config()).empty


def test_window_sufficiency_uses_count_then_observed_span_priority() -> None:
    from apps.api.seawatch.trajectories.windowing import build_feature_windows

    start = pd.Timestamp("2024-01-01T00:00:00Z")
    sufficient_offsets = [0, 120, 240, 360, 480, 600, 720, 840, 960, 1200, 1800]
    count_offsets = [0, 150, 300, 450, 600, 750, 900, 1050, 1200, 1800]
    span_offsets = [0, 100, 200, 300, 400, 500, 600, 700, 800, 1199, 1800]
    cases = [
        ("track-sufficient", sufficient_offsets, "sufficient", 10),
        ("track-count", count_offsets, "insufficient_observations", 9),
        ("track-span", span_offsets, "insufficient_span", 10),
    ]
    observations_parts = []
    segments_parts = []
    for track_id, offsets, _, _ in cases:
        observations, segments = _segment(
            [start + pd.Timedelta(seconds=value) for value in offsets],
            track_id=track_id,
        )
        observations_parts.append(observations)
        segments_parts.append(segments)
    observations = pd.concat(observations_parts, ignore_index=True)
    segments = pd.concat(segments_parts, ignore_index=True)

    windows = build_feature_windows(observations, segments, _config())
    first_by_track = windows.groupby("track_id", sort=False).first()

    for track_id, _, expected_status, expected_count in cases:
        row = first_by_track.loc[track_id]
        assert row["window_quality_status"] == expected_status
        assert row["observation_count"] == expected_count


def test_duplicate_timestamp_is_counted_without_changing_membership() -> None:
    from apps.api.seawatch.trajectories.windowing import build_feature_windows

    start = pd.Timestamp("2024-01-01T00:00:00Z")
    offsets = [0, 0, 180, 360, 540, 720, 900, 1080, 1260, 1440, 1800]
    observations, segments = _segment(
        [start + pd.Timedelta(seconds=value) for value in offsets]
    )

    window = build_feature_windows(observations, segments, _config()).iloc[0]

    assert window["zero_duration_interval_count"] == 1
    assert len(window["_observation_positions"]) == 10
