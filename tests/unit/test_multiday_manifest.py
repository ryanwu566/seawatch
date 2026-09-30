from __future__ import annotations

from datetime import date
import json
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from apps.api.seawatch.adapters.noaa_ais import sha256_file
from apps.api.seawatch.datasets.multiday_manifest import (
    build_phase3a_manifest,
    load_daily_lineage,
    render_phase3a_report,
)
from apps.api.seawatch.datasets.source_catalog import load_phase3a_catalog
from apps.api.seawatch.trajectories.contracts import PHASE1_COLUMNS
from apps.api.seawatch.trajectories.features import FEATURE_COLUMNS


CATALOG_PATH = Path("config/noaa_ais_phase3a_dates.json")
CONFIG_HASH = "70aa8dd26c6f438c5122b48a497aad426fc5e4661829ff54611a266048f92a02"


def _write_parquet(path: Path, frame: pd.DataFrame, metadata: dict[str, str]) -> None:
    table = pa.Table.from_pandas(frame, preserve_index=False)
    encoded = {key.encode(): value.encode() for key, value in metadata.items()}
    pq.write_table(table.replace_schema_metadata(encoded), path)


def _daily_fixture(root: Path, source_date: date, *, windows: int = 2) -> tuple[Path, Path]:
    column_map = root / "config/noaa_ais_2024_columns.json"
    if not column_map.exists():
        column_map.parent.mkdir(parents=True, exist_ok=True)
        column_map.write_bytes(Path("config/noaa_ais_2024_columns.json").read_bytes())
    rendered = source_date.isoformat()
    start = pd.Timestamp(f"{rendered}T00:00:00Z")
    phase1_path = root / f"{rendered}-phase1.parquet"
    phase1_manifest_path = root / f"{rendered}-phase1.json"
    feature_manifest_path = root / f"{rendered}-features.json"
    phase1 = pd.DataFrame(
        {
            "track_id": [f"safe-{rendered}"] * 2,
            "base_date_time": [start, start + pd.Timedelta(minutes=30)],
            "longitude": [-122.4, -122.39],
            "latitude": [37.8, 37.81],
            "sog": [5.0, 6.0],
            "cog": [90.0, 91.0],
            "heading": [90.0, 91.0],
            "vessel_type": [70, 70],
        }
    ).loc[:, PHASE1_COLUMNS]
    _write_parquet(
        phase1_path,
        phase1,
        {"seawatch_crs": "EPSG:4326", "seawatch_timezone": "UTC"},
    )
    entry = load_phase3a_catalog(CATALOG_PATH).for_date(source_date)
    phase1_manifest = {
        "dataset_id": f"noaa-ais-{rendered}-sf-bay-cargo-smoke",
        "source_date": rendered,
        "source_url": entry.source_url,
        "publisher": "NOAA Office for Coastal Management",
        "observed_license": "CC0 1.0 Universal",
        "crs": "EPSG:4326",
        "timezone": "UTC",
        "geographic_bbox": {"west": -122.55, "south": 37.68, "east": -122.25, "north": 37.9},
        "vessel_type_filter": {"field": "vessel_type", "codes": list(range(70, 80))},
        "output_columns": list(PHASE1_COLUMNS),
        "output_rows": 2,
        "source_rows": 10,
        "bbox_rows": 4,
        "filtered_rows": 2,
        "processing_version": "phase1-v1",
    }
    phase1_manifest_path.write_text(json.dumps(phase1_manifest), encoding="utf-8")

    segmented_path = root / f"{rendered}-segmented.parquet"
    segments_path = root / f"{rendered}-segments.parquet"
    windows_path = root / f"{rendered}-windows.parquet"
    segmented = phase1.assign(segment_id=f"safe-segment-{rendered}")
    segments = pd.DataFrame(
        {
            "track_id": [f"safe-{rendered}"],
            "segment_id": [f"safe-segment-{rendered}"],
            "segment_start_utc": [start],
            "segment_end_utc": [start + pd.Timedelta(minutes=30)],
            "segment_duration_seconds": [1800.0],
            "observation_count": [2],
        }
    )
    window_rows = []
    for index in range(windows):
        row = {
            "track_id": f"safe-{rendered}",
            "segment_id": f"safe-segment-{rendered}",
            "window_id": f"safe-window-{rendered}-{index}",
            "window_start_utc": start + pd.Timedelta(minutes=5 * index),
            "window_end_utc": start + pd.Timedelta(minutes=30 + 5 * index),
            "first_observation_utc": start,
            "last_observation_utc": start + pd.Timedelta(minutes=20),
            "window_quality_status": "sufficient" if index == 0 else "insufficient_observations",
            "max_gap_seconds": 300.0,
        }
        row.update({name: (1.0 if index == 0 else None) for name in FEATURE_COLUMNS})
        window_rows.append(row)
    window_frame = pd.DataFrame(
        window_rows,
        columns=[
            "track_id", "segment_id", "window_id", "window_start_utc",
            "window_end_utc", "first_observation_utc", "last_observation_utc",
            "window_quality_status", "max_gap_seconds", *FEATURE_COLUMNS,
        ],
    )
    artifact_metadata = {
        "seawatch_schema_version": "trajectory-features-v1",
        "seawatch_crs": "EPSG:4326",
        "seawatch_timezone": "UTC",
        "seawatch_source_artifact_sha256": sha256_file(phase1_path),
        "seawatch_source_manifest_sha256": sha256_file(phase1_manifest_path),
        "seawatch_config_sha256": CONFIG_HASH,
        "seawatch_generator_version": "phase2-v1",
        "seawatch_feature_units": "{}",
    }
    for path, frame in (
        (segmented_path, segmented),
        (segments_path, segments),
        (windows_path, window_frame),
    ):
        _write_parquet(path, frame, artifact_metadata)

    def artifact(path: Path, rows: int) -> dict[str, object]:
        return {
            "path": path.name,
            "size_bytes": path.stat().st_size,
            "row_count": rows,
            "sha256": sha256_file(path),
        }

    accepted = 1 if windows else 0
    missingness = {
        name: {
            "missing_count": max(0, windows - accepted),
            "missing_rate": ((windows - accepted) / windows if windows else None),
        }
        for name in FEATURE_COLUMNS
    }
    distribution = {
        "count": windows,
        "missing_count": 0,
        "missing_rate": (0.0 if windows else None),
        "minimum": (1.0 if windows else None),
        "p25": (1.0 if windows else None),
        "median": (1.0 if windows else None),
        "p75": (1.0 if windows else None),
        "p95": (1.0 if windows else None),
        "maximum": (1.0 if windows else None),
    }
    feature_manifest = {
        "schema_version": "trajectory-features-v1",
        "dataset_id": f"features-{rendered}",
        "source_dataset_id": phase1_manifest["dataset_id"],
        "source_date": rendered,
        "source_artifact": {
            "path": phase1_path.name,
            "size_bytes": phase1_path.stat().st_size,
            "sha256": sha256_file(phase1_path),
        },
        "source_manifest": {
            "path": phase1_manifest_path.name,
            "sha256": sha256_file(phase1_manifest_path),
        },
        "configuration": {
            "path": "config/trajectory_features_v1.json",
            "sha256": CONFIG_HASH,
            "values": {"window_duration_seconds": 1800.0, "window_stride_seconds": 300.0},
        },
        "input_rows": 2,
        "input_track_count": 1,
        "segment_count": 1,
        "candidate_window_count": windows,
        "accepted_window_count": accepted,
        "rejected_window_count": max(0, windows - accepted),
        "rejection_reasons": ({"insufficient_observations": windows - accepted} if windows > accepted else {}),
        "feature_columns": list(FEATURE_COLUMNS),
        "feature_missingness": missingness,
        "distributions": {
            name: dict(distribution)
            for name in (
                "segments_per_track", "segment_duration_seconds", "observations_per_segment",
                "windows_per_track", "windows_per_segment", "max_gap_seconds",
                "input_sog_knots", "course_change_abs_sum_deg", "course_change_abs_p95_deg",
                "path_distance_m", "displacement_m", "path_displacement_ratio",
                "low_speed_fraction", "low_speed_duration_seconds",
            )
        },
        "validation": {"invalid_sog_rows": 0, "invalid_cog_rows": 0, "invalid_heading_rows": 0},
        "artifacts": {
            "segmented": artifact(segmented_path, len(segmented)),
            "segments": artifact(segments_path, len(segments)),
            "windows": artifact(windows_path, len(window_frame)),
        },
    }
    feature_manifest_path.write_text(json.dumps(feature_manifest), encoding="utf-8")
    return phase1_manifest_path, feature_manifest_path


def test_builds_fixed_split_aggregate_without_row_level_ids(tmp_path: Path) -> None:
    catalog = load_phase3a_catalog(CATALOG_PATH)
    lineages = []
    for index, entry in enumerate(catalog.entries):
        phase1, features = _daily_fixture(tmp_path, entry.date, windows=0 if index == 2 else 2)
        lineages.append(load_daily_lineage(entry, phase1, features, root=tmp_path))

    manifest = build_phase3a_manifest(catalog, lineages)
    report = render_phase3a_report(manifest)

    assert manifest["schema_version"] == "phase3a-multiday-v1"
    assert [item["split_role"] for item in manifest["dates"]] == ["train", "calibration", "test"]
    assert manifest["totals"] == {
        "observations": 6,
        "tracks": 3,
        "segments": 3,
        "candidate_windows": 4,
        "accepted_windows": 2,
        "rejected_windows": 2,
    }
    assert manifest["dates"][2]["qa"]["distributions"]["windows_per_track"]["minimum"] == 0.0
    assert manifest["dates"][2]["qa"]["distributions"]["path_distance_m"]["median"] is None
    assert manifest["shared_contract"]["feature_config_sha256"] == CONFIG_HASH
    assert manifest["phase3b_readiness"]["decision"].startswith("B.")
    public_text = (json.dumps(manifest) + report).casefold()
    assert "safe-2024" not in public_text
    assert "mmsi" not in public_text
    assert "calibration" in report


def test_rejects_feature_configuration_mismatch(tmp_path: Path) -> None:
    catalog = load_phase3a_catalog(CATALOG_PATH)
    lineages = []
    for entry in catalog.entries:
        phase1, features = _daily_fixture(tmp_path, entry.date)
        lineages.append(load_daily_lineage(entry, phase1, features, root=tmp_path))

    from dataclasses import replace

    altered_manifest = dict(lineages[1].feature_manifest)
    altered_configuration = dict(altered_manifest["configuration"])
    altered_configuration["sha256"] = "b" * 64
    altered_manifest["configuration"] = altered_configuration
    lineages[1] = replace(lineages[1], feature_manifest=altered_manifest)

    with pytest.raises(ValueError, match="feature configuration hash"):
        build_phase3a_manifest(catalog, lineages)


def test_rejects_incomplete_changed_role_and_source_schema(tmp_path: Path) -> None:
    from dataclasses import replace

    catalog = load_phase3a_catalog(CATALOG_PATH)
    lineages = []
    for entry in catalog.entries:
        phase1, features = _daily_fixture(tmp_path, entry.date)
        lineages.append(load_daily_lineage(entry, phase1, features, root=tmp_path))

    with pytest.raises(ValueError, match="exactly the approved"):
        build_phase3a_manifest(catalog, lineages[:2])
    with pytest.raises(ValueError, match="split role"):
        build_phase3a_manifest(
            catalog, [lineages[0], replace(lineages[1], split_role="test"), lineages[2]]
        )
    changed_manifest = dict(lineages[2].phase1_manifest)
    changed_manifest["source_columns"] = [{"name": "changed", "type": "string"}]
    with pytest.raises(ValueError, match="source_columns"):
        build_phase3a_manifest(
            catalog,
            [lineages[0], lineages[1], replace(lineages[2], phase1_manifest=changed_manifest)],
        )


def test_rejects_hash_mismatch_and_timestamp_spill(tmp_path: Path) -> None:
    catalog = load_phase3a_catalog(CATALOG_PATH)
    entry = catalog.entries[0]
    phase1, features = _daily_fixture(tmp_path, entry.date)
    payload = json.loads(features.read_text(encoding="utf-8"))
    payload["source_artifact"]["sha256"] = "0" * 64
    features.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="source artifact hash"):
        load_daily_lineage(entry, phase1, features, root=tmp_path)

    phase1, features = _daily_fixture(tmp_path, entry.date)
    feature_payload = json.loads(features.read_text(encoding="utf-8"))
    source_path = tmp_path / feature_payload["source_artifact"]["path"]
    frame = pq.read_table(source_path).to_pandas()
    frame.loc[0, "base_date_time"] = pd.Timestamp("2024-01-02T00:00:00Z")
    _write_parquet(source_path, frame, {"seawatch_crs": "EPSG:4326", "seawatch_timezone": "UTC"})
    feature_payload["source_artifact"]["sha256"] = sha256_file(source_path)
    feature_payload["source_artifact"]["size_bytes"] = source_path.stat().st_size
    features.write_text(json.dumps(feature_payload), encoding="utf-8")
    with pytest.raises(ValueError, match="outside source date"):
        load_daily_lineage(entry, phase1, features, root=tmp_path)


def test_rejects_forbidden_public_column(tmp_path: Path) -> None:
    catalog = load_phase3a_catalog(CATALOG_PATH)
    entry = catalog.entries[0]
    phase1, features = _daily_fixture(tmp_path, entry.date)
    payload = json.loads(features.read_text(encoding="utf-8"))
    windows_path = tmp_path / payload["artifacts"]["windows"]["path"]
    frame = pq.read_table(windows_path).to_pandas()
    frame["mmsi"] = 123456789
    metadata = {key.decode(): value.decode() for key, value in (pq.read_schema(windows_path).metadata or {}).items()}
    _write_parquet(windows_path, frame, metadata)
    payload["artifacts"]["windows"]["sha256"] = sha256_file(windows_path)
    payload["artifacts"]["windows"]["size_bytes"] = windows_path.stat().st_size
    features.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="forbidden"):
        load_daily_lineage(entry, phase1, features, root=tmp_path)
