from __future__ import annotations

from datetime import date

import pandas as pd
import pytest
from shapely.geometry import Point

from apps.api.seawatch.trajectories.preprocess import (
    BoundingBox,
    bbox_mask,
    canonicalize_observations,
    cargo_vessel_mask,
    order_and_deduplicate,
    parse_utc_timestamps,
    summarize_time_gaps,
    select_complete_tracks,
    surrogate_track_id,
    validate_source_date_range,
    valid_coordinate_mask,
)


def test_parse_utc_timestamps_normalizes_naive_and_offset_values() -> None:
    values = pd.Series(
        ["2024-01-01 00:00:00", "2024-01-01T01:00:00+01:00"]
    )

    result = parse_utc_timestamps(values)

    expected = pd.Timestamp("2024-01-01T00:00:00Z")
    assert result.tolist() == [expected, expected]
    assert str(result.dtype) == "datetime64[us, UTC]"


def test_parse_utc_timestamps_marks_invalid_values_missing() -> None:
    result = parse_utc_timestamps(pd.Series(["not-a-time", None]))

    assert result.isna().tolist() == [True, True]


def test_validate_source_date_range_accepts_only_the_selected_utc_day() -> None:
    validate_source_date_range(
        pd.Timestamp("2024-01-02T00:00:00Z"),
        pd.Timestamp("2024-01-02T23:59:59.999999Z"),
        date(2024, 1, 2),
    )


@pytest.mark.parametrize(
    ("minimum", "maximum"),
    [
        ("2024-01-01T23:59:59Z", "2024-01-02T12:00:00Z"),
        ("2024-01-02T12:00:00Z", "2024-01-03T00:00:00Z"),
    ],
)
def test_validate_source_date_range_rejects_observations_outside_selected_day(
    minimum: str, maximum: str
) -> None:
    with pytest.raises(ValueError, match="outside selected source date 2024-01-02"):
        validate_source_date_range(
            pd.Timestamp(minimum), pd.Timestamp(maximum), date(2024, 1, 2)
        )


def test_valid_coordinate_mask_rejects_null_nonfinite_and_out_of_range() -> None:
    longitude = pd.Series([-180.0, 180.0, None, float("nan"), float("inf"), 180.1, 0])
    latitude = pd.Series([-90.0, 90.0, 0, 0, 0, 0, -90.1])

    assert valid_coordinate_mask(longitude, latitude).tolist() == [
        True,
        True,
        False,
        False,
        False,
        False,
        False,
    ]


def test_bbox_mask_includes_edges_and_excludes_just_outside() -> None:
    bbox = BoundingBox(west=-122.55, south=37.68, east=-122.25, north=37.90)
    longitude = pd.Series([-122.55, -122.25, -122.550001, -122.249999, -122.4])
    latitude = pd.Series([37.68, 37.90, 37.8, 37.8, 37.900001])

    assert bbox_mask(longitude, latitude, bbox).tolist() == [
        True,
        True,
        False,
        False,
        False,
    ]


def test_cargo_vessel_mask_accepts_only_integer_codes_70_through_79() -> None:
    values = pd.Series([69, 70, 79, 80, None, "70", 70.5])

    assert cargo_vessel_mask(values).tolist() == [
        False,
        True,
        True,
        False,
        False,
        True,
        False,
    ]


def test_canonicalize_observations_decodes_wkb_and_keeps_present_fields() -> None:
    frame = pd.DataFrame(
        {
            "MMSI": ["fixture-vessel"],
            "BaseDateTime": ["2024-01-01 00:00:00"],
            "Geometry": [Point(-122.4, 37.8).wkb],
            "SOG": [12.5],
        }
    )

    result = canonicalize_observations(
        frame,
        {
            "source_vessel_id": "MMSI",
            "base_date_time": "BaseDateTime",
            "geometry": "Geometry",
            "sog": "SOG",
        },
        source_crs="EPSG:4326",
    )

    assert result.columns.tolist() == [
        "source_vessel_id",
        "base_date_time",
        "longitude",
        "latitude",
        "sog",
    ]
    assert result.loc[0, "longitude"] == pytest.approx(-122.4)
    assert result.loc[0, "latitude"] == pytest.approx(37.8)
    assert result.loc[0, "base_date_time"] == pd.Timestamp("2024-01-01T00:00:00Z")
    assert "cog" not in result


def test_canonicalize_observations_transforms_verified_projected_crs() -> None:
    frame = pd.DataFrame(
        {
            "id": ["vessel"],
            "time": ["2024-01-01T00:00:00Z"],
            "geometry": [Point(1113194.9079327357, 0).wkb],
        }
    )

    result = canonicalize_observations(
        frame,
        {
            "source_vessel_id": "id",
            "base_date_time": "time",
            "geometry": "geometry",
        },
        source_crs="EPSG:3857",
    )

    assert result.loc[0, "longitude"] == pytest.approx(10.0)
    assert result.loc[0, "latitude"] == pytest.approx(0.0)


def test_canonicalize_observations_rejects_missing_required_field() -> None:
    frame = pd.DataFrame(
        {"time": ["2024-01-01T00:00:00Z"], "geometry": [Point(0, 0).wkb]}
    )

    with pytest.raises(ValueError, match="source_vessel_id"):
        canonicalize_observations(
            frame,
            {"base_date_time": "time", "geometry": "geometry"},
            source_crs="EPSG:4326",
        )


def test_canonicalize_observations_rejects_ambiguous_crs() -> None:
    frame = pd.DataFrame(
        {
            "id": [1],
            "time": ["2024-01-01T00:00:00Z"],
            "geometry": [Point(0, 0).wkb],
        }
    )

    with pytest.raises(ValueError, match="source CRS"):
        canonicalize_observations(
            frame,
            {
                "source_vessel_id": "id",
                "base_date_time": "time",
                "geometry": "geometry",
            },
            source_crs=None,
        )


def test_surrogate_track_id_is_stable_dataset_scoped_and_non_displaying() -> None:
    first = surrogate_track_id("sample-vessel", date(2024, 1, 1))
    normalized = surrogate_track_id(" sample-vessel ", date(2024, 1, 1))

    assert first == "fb051096f6c6ee76"
    assert normalized == first
    assert surrogate_track_id("other-vessel", date(2024, 1, 1)) != first
    assert surrogate_track_id("sample-vessel", date(2024, 1, 2)) != first
    assert len(first) == 16
    assert first.isascii() and first.isalnum() and first == first.lower()
    assert "sample-vessel" not in first


def test_order_and_deduplicate_sorts_stably_and_removes_only_exact_duplicates() -> None:
    frame = pd.DataFrame(
        [
            {"source_vessel_id": "b", "base_date_time": "2024-01-01T00:02:00Z", "longitude": 0.0, "latitude": 0.0, "sog": 999.0},
            {"source_vessel_id": "a", "base_date_time": "2024-01-01T00:01:00Z", "longitude": 1.0, "latitude": 1.0, "sog": 5.0},
            {"source_vessel_id": "a", "base_date_time": "2024-01-01T00:00:00Z", "longitude": 2.0, "latitude": 2.0, "sog": 4.0},
            {"source_vessel_id": "a", "base_date_time": "2024-01-01T00:00:00Z", "longitude": 2.0, "latitude": 2.0, "sog": 4.0},
            {"source_vessel_id": "a", "base_date_time": "2024-01-01T00:00:00Z", "longitude": 2.1, "latitude": 2.1, "sog": 6.0},
        ]
    )
    frame["base_date_time"] = pd.to_datetime(frame["base_date_time"], utc=True)

    result, stats = order_and_deduplicate(frame)

    assert result[["source_vessel_id", "sog"]].values.tolist() == [
        ["a", 4.0],
        ["a", 6.0],
        ["a", 5.0],
        ["b", 999.0],
    ]
    assert stats.exact_duplicate_rows == 1
    assert stats.duplicate_timestamp_rows == 2
    assert stats.duplicate_timestamp_groups == 1
    assert 999.0 in result["sog"].tolist()
    assert "_source_row_order" not in result


def test_summarize_time_gaps_stays_within_vessels_and_does_not_interpolate() -> None:
    frame = pd.DataFrame(
        {
            "source_vessel_id": ["a", "a", "a", "b", "b", "b"],
            "base_date_time": pd.to_datetime(
                [
                    "2024-01-01T00:00:00Z",
                    "2024-01-01T00:00:00Z",
                    "2024-01-01T00:20:00Z",
                    "2024-01-01T00:05:00Z",
                    "2024-01-01T00:04:00Z",
                    "2024-01-01T00:14:00Z",
                ],
                utc=True,
            ),
        }
    )
    original_rows = len(frame)

    stats = summarize_time_gaps(frame, threshold_minutes=10)

    assert stats.observation_pairs == 4
    assert stats.positive_gap_count == 2
    assert stats.zero_gap_count == 1
    assert stats.negative_gap_count == 1
    assert stats.gaps_over_threshold_count == 1
    assert stats.minimum_positive_seconds == 600.0
    assert stats.median_positive_seconds == 900.0
    assert stats.maximum_positive_seconds == 1200.0
    assert stats.threshold_seconds == 600.0
    assert len(frame) == original_rows


def _selection_frame(track_sizes: dict[str, int]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for track_id, size in track_sizes.items():
        for minute in range(size):
            rows.append(
                {
                    "track_id": track_id,
                    "base_date_time": pd.Timestamp(
                        f"2024-01-01T00:{minute:02d}:00Z"
                    ),
                    "longitude": float(minute),
                    "latitude": 0.0,
                }
            )
    return pd.DataFrame(rows)


def test_select_complete_tracks_retains_every_row_below_ceiling() -> None:
    frame = _selection_frame({"b": 2, "a": 2})

    result, stats = select_complete_tracks(frame, max_observations=5)

    assert len(result) == 4
    assert result.groupby("track_id").size().to_dict() == {"a": 2, "b": 2}
    assert stats.selected_rows == 4
    assert stats.selected_tracks == 2
    assert stats.skipped_track_ids == ()


def test_select_complete_tracks_is_deterministic_and_never_partial() -> None:
    frame = _selection_frame({"b": 3, "c": 2, "a": 3})

    first, first_stats = select_complete_tracks(frame, max_observations=5)
    shuffled, shuffled_stats = select_complete_tracks(
        frame.sample(frac=1, random_state=42), max_observations=5
    )

    assert first.groupby("track_id").size().to_dict() == {"a": 3, "c": 2}
    assert shuffled[["track_id", "base_date_time"]].values.tolist() == first[
        ["track_id", "base_date_time"]
    ].values.tolist()
    assert first_stats.skipped_track_ids == ("b",)
    assert shuffled_stats == first_stats


def test_select_complete_tracks_skips_oversized_history_without_truncating() -> None:
    frame = _selection_frame({"huge": 6, "small": 2})

    result, stats = select_complete_tracks(frame, max_observations=5)

    assert result.groupby("track_id").size().to_dict() == {"small": 2}
    assert stats.oversized_track_ids == ("huge",)
    assert stats.skipped_track_ids == ("huge",)
    assert stats.input_rows == 8
    assert stats.selected_rows == 2


def test_preparation_rejects_ceiling_that_admits_no_complete_track() -> None:
    frame = pd.DataFrame(
        {
            "id": ["vessel", "vessel"],
            "time": ["2024-01-01T00:00:00Z", "2024-01-01T00:01:00Z"],
            "longitude": [-122.4, -122.39],
            "latitude": [37.8, 37.81],
            "vessel_type": [70, 70],
        }
    )

    with pytest.raises(ValueError, match=r"no complete tracks fit.*skipped=1.*oversized=1"):
        from apps.api.seawatch.trajectories.preprocess import prepare_smoke_dataset

        prepare_smoke_dataset(
            frame,
            {
                "source_vessel_id": "id",
                "base_date_time": "time",
                "longitude": "longitude",
                "latitude": "latitude",
                "vessel_type": "vessel_type",
            },
            source_crs="EPSG:4326",
            source_date=date(2024, 1, 1),
            bbox=BoundingBox(-122.55, 37.68, -122.25, 37.90),
            max_observations=1,
        )


def test_preparation_normalizes_identifiers_before_deduplication_and_gaps() -> None:
    from apps.api.seawatch.trajectories.preprocess import prepare_smoke_dataset

    frame = pd.DataFrame(
        {
            "id": ["vessel", " vessel "],
            "time": ["2024-01-01T00:00:00Z", "2024-01-01T00:00:00Z"],
            "longitude": [-122.4, -122.4],
            "latitude": [37.8, 37.8],
            "vessel_type": [70, 70],
        }
    )

    result = prepare_smoke_dataset(
        frame,
        {
            "source_vessel_id": "id",
            "base_date_time": "time",
            "longitude": "longitude",
            "latitude": "latitude",
            "vessel_type": "vessel_type",
        },
        source_crs="EPSG:4326",
        source_date=date(2024, 1, 1),
        bbox=BoundingBox(-122.55, 37.68, -122.25, 37.90),
    )

    assert result.output_rows == 1
    assert result.vessel_count == 1
    assert result.duplicate_stats.exact_duplicate_rows == 1
    assert result.time_gap_stats.observation_pairs == 0
