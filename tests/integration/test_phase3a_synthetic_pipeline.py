from __future__ import annotations

from dataclasses import asdict
from datetime import date
import json
from pathlib import Path

import pandas as pd

from apps.api.seawatch.adapters.noaa_ais import sha256_file
from apps.api.seawatch.datasets.multiday_manifest import DailyLineage, build_phase3a_manifest
from apps.api.seawatch.datasets.source_catalog import load_phase3a_catalog
from apps.api.seawatch.trajectories.contracts import load_feature_config, validate_observations
from apps.api.seawatch.trajectories.features import FEATURE_COLUMNS, compute_window_features
from apps.api.seawatch.trajectories.preprocess import BoundingBox, prepare_smoke_dataset
from apps.api.seawatch.trajectories.segmentation import segment_observations
from apps.api.seawatch.trajectories.windowing import build_feature_windows


def _source_frame(source_date: date) -> pd.DataFrame:
    start = pd.Timestamp(source_date, tz="UTC")
    timestamps = [start + pd.Timedelta(seconds=150 * index) for index in range(13)]
    return pd.DataFrame(
        {
            "id": ["same-private-source-id"] * len(timestamps),
            "time": timestamps,
            "longitude": [-122.45 + 0.001 * index for index in range(len(timestamps))],
            "latitude": [37.8] * len(timestamps),
            "sog": [6.0] * len(timestamps),
            "cog": [90.0] * len(timestamps),
            "heading": [90.0] * len(timestamps),
            "vessel_type": [70] * len(timestamps),
        }
    )


def test_three_dates_flow_independently_into_fixed_cohort() -> None:
    catalog = load_phase3a_catalog(Path("config/noaa_ais_phase3a_dates.json"))
    config_path = Path("config/trajectory_features_v1.json")
    config = load_feature_config(config_path)
    config_hash = sha256_file(config_path)
    lineages = []
    observed_track_ids: list[str] = []

    for entry in catalog.entries:
        prepared = prepare_smoke_dataset(
            _source_frame(entry.date),
            {
                "source_vessel_id": "id",
                "base_date_time": "time",
                "longitude": "longitude",
                "latitude": "latitude",
                "sog": "sog",
                "cog": "cog",
                "heading": "heading",
                "vessel_type": "vessel_type",
            },
            source_crs="EPSG:4326",
            source_date=entry.date,
            bbox=BoundingBox(-122.55, 37.68, -122.25, 37.90),
        )
        validated = validate_observations(prepared.frame)
        segmentation = segment_observations(validated.frame, config)
        private_windows = build_feature_windows(
            segmentation.observations, segmentation.segments, config
        )
        windows = compute_window_features(
            segmentation.observations, private_windows, config
        )
        observed_track_ids.extend(prepared.frame["track_id"].unique().tolist())
        day_start = pd.Timestamp(entry.date, tz="UTC")
        day_end = day_start + pd.Timedelta(days=1)
        assert prepared.frame["base_date_time"].between(day_start, day_end, inclusive="left").all()
        assert segmentation.observations["base_date_time"].between(day_start, day_end, inclusive="left").all()
        assert windows["first_observation_utc"].between(day_start, day_end, inclusive="left").all()
        assert windows["last_observation_utc"].between(day_start, day_end, inclusive="left").all()
        assert len(segmentation.segments) == 1
        assert len(windows) == 1
        assert windows["window_quality_status"].tolist() == ["sufficient"]

        feature_missingness = {
            name: {
                "missing_count": int(windows[name].isna().sum()),
                "missing_rate": float(windows[name].isna().mean()),
            }
            for name in FEATURE_COLUMNS
        }
        phase1_manifest = {
            "publisher": "NOAA Office for Coastal Management",
            "observed_license": "CC0 1.0 Universal",
            "crs": "EPSG:4326",
            "timezone": "UTC",
            "geographic_bbox": {"west": -122.55, "south": 37.68, "east": -122.25, "north": 37.9},
            "vessel_type_filter": {"field": "vessel_type", "codes": list(range(70, 80))},
            "output_columns": list(prepared.frame.columns),
            "processing_version": "phase1-v1",
        }
        feature_manifest = {
            "configuration": {"sha256": config_hash, "values": asdict(config)}
        }
        qa = {
            "observations": len(prepared.frame),
            "tracks": prepared.vessel_count,
            "segments": len(segmentation.segments),
            "candidate_windows": len(windows),
            "accepted_windows": 1,
            "rejected_windows": 0,
            "rejection_reasons": {},
            "feature_missingness": feature_missingness,
            "distributions": {},
            "validation": asdict(validated.stats),
            "maximum_accepted_window_track_share": 1.0,
            "nominal_overlap_factor": config.window_duration_seconds / config.window_stride_seconds,
            "approximate_non_overlapping_windows": 0,
        }
        lineages.append(
            DailyLineage(
                source_date=entry.date,
                split_role=entry.split_role,
                phase1_manifest_path=Path(f"{entry.date}-phase1.json"),
                feature_manifest_path=Path(f"{entry.date}-features.json"),
                phase1_manifest_sha256="a" * 64,
                feature_manifest_sha256="b" * 64,
                column_map_sha256=sha256_file(Path("config/noaa_ais_2024_columns.json")),
                phase1_manifest=phase1_manifest,
                feature_manifest=feature_manifest,
                source_artifact={"path": f"{entry.date}.parquet", "sha256": "c" * 64},
                feature_artifacts={},
                qa=qa,
            )
        )

    manifest = build_phase3a_manifest(catalog, lineages)

    assert len(set(observed_track_ids)) == 3
    assert [item["split_role"] for item in manifest["dates"]] == ["train", "calibration", "test"]
    assert manifest["shared_contract"]["feature_config_sha256"] == config_hash
    assert manifest["shared_contract"]["feature_columns"] == list(FEATURE_COLUMNS)
    assert manifest["totals"]["observations"] == 39
    public = json.dumps(manifest).casefold()
    assert "same-private-source-id" not in public
    for track_id in observed_track_ids:
        assert track_id not in public
