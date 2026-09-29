from __future__ import annotations

from datetime import date, datetime, timezone
import json
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from apps.api.seawatch.trajectories.preprocess import (
    BoundingBox,
    build_manifest,
    prepare_smoke_dataset,
    prepare_smoke_dataset_batches,
    render_qa_report,
    write_geojson_preview,
    write_processed_parquet,
)


SF_BAY = BoundingBox(west=-122.55, south=37.68, east=-122.25, north=37.90)
COLUMN_MAP = {
    "source_vessel_id": "MMSI",
    "base_date_time": "BaseDateTime",
    "longitude": "LON",
    "latitude": "LAT",
    "sog": "SOG",
    "cog": "COG",
    "heading": "Heading",
    "vessel_type": "VesselType",
}


def _source_frame() -> pd.DataFrame:
    rows = [
        ["vessel-alpha", "2024-01-01T00:20:00Z", -122.40, 37.80, 15.0, 90.0, 90.0, 70],
        ["vessel-alpha", "2024-01-01T00:00:00Z", -122.41, 37.81, 10.0, 80.0, 80.0, 70],
        ["vessel-alpha", "2024-01-01T00:00:00Z", -122.41, 37.81, 10.0, 80.0, 80.0, 70],
        ["vessel-alpha", "2024-01-01T00:00:00Z", -122.42, 37.82, 11.0, 81.0, 81.0, 70],
        ["vessel-beta", "2024-01-01T00:00:00Z", -122.35, 37.75, None, None, None, 79],
        ["vessel-beta", "2024-01-01T00:05:00Z", -122.34, 37.76, 8.0, 45.0, 45.0, 79],
        ["invalid-coordinate", "2024-01-01T00:00:00Z", 999.0, 37.80, 1.0, 1.0, 1.0, 70],
        ["outside-bbox", "2024-01-01T00:00:00Z", -123.00, 37.80, 1.0, 1.0, 1.0, 70],
        ["non-cargo", "2024-01-01T00:00:00Z", -122.40, 37.80, 1.0, 1.0, 1.0, 60],
        ["invalid-time", "invalid", -122.40, 37.80, 1.0, 1.0, 1.0, 70],
    ]
    return pd.DataFrame(
        rows,
        columns=["MMSI", "BaseDateTime", "LON", "LAT", "SOG", "COG", "Heading", "VesselType"],
    )


def test_synthetic_observations_flow_to_ordered_private_safe_parquet(
    tmp_path: Path,
) -> None:
    result = prepare_smoke_dataset(
        _source_frame(),
        COLUMN_MAP,
        source_crs="EPSG:4326",
        source_date=date(2024, 1, 1),
        bbox=SF_BAY,
        max_observations=50_000,
    )

    assert result.source_rows == 10
    assert result.invalid_coordinate_rows == 1
    assert result.invalid_timestamp_rows == 1
    assert result.bbox_rows == 7
    assert result.filtered_rows == 6
    assert result.output_rows == 5
    assert result.vessel_count == 2
    assert result.duplicate_stats.exact_duplicate_rows == 1
    assert result.time_gap_stats.gaps_over_threshold_count == 1
    assert result.frame.groupby("track_id").size().to_dict() == {
        "2b675ebcce43a986": 3,
        "96b8f125cc0bb6b0": 2,
    }
    assert result.frame.groupby("track_id")["base_date_time"].apply(
        lambda values: values.is_monotonic_increasing
    ).all()
    assert "source_vessel_id" not in result.frame
    assert "MMSI" not in result.frame

    output = tmp_path / "processed.parquet"
    artifact = write_processed_parquet(result.frame, output)
    written = pq.read_table(output).to_pandas()

    assert artifact.row_count == 5
    assert artifact.size_bytes == output.stat().st_size
    assert written.columns.tolist() == result.frame.columns.tolist()
    assert written["base_date_time"].dt.tz is not None
    assert b"seawatch_crs" in (pq.read_schema(output).metadata or {})


def test_geojson_preview_contains_complete_tracks_without_source_identifiers(
    tmp_path: Path,
) -> None:
    result = prepare_smoke_dataset(
        _source_frame(),
        COLUMN_MAP,
        source_crs="EPSG:4326",
        source_date=date(2024, 1, 1),
        bbox=SF_BAY,
    )
    path = tmp_path / "preview.geojson"

    artifact = write_geojson_preview(result.frame, path, max_tracks=1)
    payload = json.loads(path.read_text(encoding="utf-8"))
    serialized = json.dumps(payload).lower()

    assert artifact.row_count == 3
    assert payload["type"] == "FeatureCollection"
    assert len(payload["features"]) == 1
    feature = payload["features"][0]
    assert feature["properties"]["track_id"] == "2b675ebcce43a986"
    assert feature["properties"]["observation_count"] == 3
    assert feature["geometry"]["type"] == "LineString"
    assert len(feature["geometry"]["coordinates"]) == 3
    assert "mmsi" not in serialized
    assert "source_vessel_id" not in serialized
    assert "vessel-alpha" not in serialized
    assert "vessel-beta" not in serialized


def test_manifest_and_qa_report_use_measured_synthetic_results(tmp_path: Path) -> None:
    result = prepare_smoke_dataset(
        _source_frame(),
        COLUMN_MAP,
        source_crs="EPSG:4326",
        source_date=date(2024, 1, 1),
        bbox=SF_BAY,
    )
    parquet_record = write_processed_parquet(result.frame, tmp_path / "processed.parquet")
    geojson_record = write_geojson_preview(
        result.frame, tmp_path / "preview.geojson", max_tracks=2
    )
    manifest = build_manifest(
        result,
        dataset_id="synthetic-test",
        publisher="Test Publisher",
        source_url="https://example.invalid/source.parquet",
        source_readme_url="https://example.invalid/readme",
        observed_license=None,
        license_url=None,
        download_utc=datetime(2024, 1, 2, tzinfo=timezone.utc),
        source_date=date(2024, 1, 1),
        content_length=1234,
        source_sha256="a" * 64,
        source_inspection={
            "row_count": 10,
            "columns": [{"name": name, "type": "synthetic", "nullable": True} for name in _source_frame().columns],
            "crs": "EPSG:4326",
        },
        bbox=SF_BAY,
        processing_version="phase1-v1",
        git_reference=None,
        notes=["Synthetic integration fixture."],
    )

    required = {
        "dataset_id", "publisher", "source_url", "source_readme_url",
        "observed_license", "license_url", "download_utc", "source_date",
        "content_length", "sha256", "geographic_bbox", "vessel_type_filter",
        "source_columns", "output_columns", "crs", "timezone", "source_rows",
        "bbox_rows", "filtered_rows", "output_rows", "surrogate_id_method",
        "processing_version", "git_commit_or_version_reference", "synthetic_fields",
        "notes",
    }
    assert required.issubset(manifest)
    assert manifest["source_rows"] == 10
    assert manifest["bbox_rows"] == 7
    assert manifest["filtered_rows"] == 6
    assert manifest["output_rows"] == 5
    assert manifest["observed_license"] is None
    assert manifest["git_commit_or_version_reference"] is None
    assert manifest["synthetic_fields"] == ["track_id", "longitude", "latitude"]
    serialized = json.dumps(manifest)
    assert "vessel-alpha" not in serialized
    assert "vessel-beta" not in serialized

    report = render_qa_report(
        result,
        source_file_size=1234,
        source_metadata_rows=10,
        processed_artifact=parquet_record,
        geojson_artifact=geojson_record,
        bbox=SF_BAY,
    )
    assert "Source metadata row count | 10" in report
    assert "BBox rows | 7" in report
    assert "Cargo-filter rows (before exact deduplication) | 6" in report
    assert "Final processed rows | 5" in report
    assert "SOG missing rate | 20.0000%" in report
    assert "Coordinate-valid source rows | 9" in report
    assert "Coordinate validity rate | 90.0000%" in report
    assert "Eligible cargo exact duplicate observations removed | 1" in report
    assert "Eligible cargo zero time gaps | 1" in report
    assert "Eligible cargo negative time gaps | 0" in report
    assert "Eligible cargo gaps greater than 10 minutes | 1" in report
    assert "before the complete-track ceiling" in report
    assert "Tracks skipped by the observation ceiling | 0" in report
    assert "vessel-alpha" not in report


def test_batched_preparation_matches_single_frame_across_batch_duplicates() -> None:
    source = _source_frame()
    expected = prepare_smoke_dataset(
        source,
        COLUMN_MAP,
        source_crs="EPSG:4326",
        source_date=date(2024, 1, 1),
        bbox=SF_BAY,
    )

    actual = prepare_smoke_dataset_batches(
        [source.iloc[:3].copy(), source.iloc[3:].copy()],
        COLUMN_MAP,
        source_crs="EPSG:4326",
        source_date=date(2024, 1, 1),
        bbox=SF_BAY,
    )

    pd.testing.assert_frame_equal(actual.frame, expected.frame)
    assert actual.source_rows == expected.source_rows
    assert actual.bbox_rows == expected.bbox_rows
    assert actual.filtered_rows == expected.filtered_rows
    assert actual.duplicate_stats == expected.duplicate_stats
    assert actual.time_gap_stats == expected.time_gap_stats
