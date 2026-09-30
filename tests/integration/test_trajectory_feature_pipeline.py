from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from apps.api.seawatch.trajectories.contracts import FORBIDDEN_PUBLIC_COLUMNS, load_feature_config, validate_observations
from apps.api.seawatch.trajectories.feature_io import write_feature_parquet
from apps.api.seawatch.trajectories.features import FEATURE_COLUMNS, FEATURE_UNITS, compute_window_features
from apps.api.seawatch.trajectories.segmentation import segment_observations
from apps.api.seawatch.trajectories.windowing import build_feature_windows


def _rows(track_id: str, offsets: list[int], kind: str) -> list[dict[str, object]]:
    origin = pd.Timestamp("2024-01-01T00:00:00Z")
    loop = [(0.0, 0.0), (0.01, 0.0), (0.01, 0.01), (0.0, 0.01)]
    rows: list[dict[str, object]] = []
    for index, offset in enumerate(offsets):
        longitude = index * 0.001
        latitude = 0.0
        sog = 8.0
        cog: float | None = 90.0
        heading: float | None = 90.0
        if kind == "wrap":
            cog = 359.0 if index % 2 == 0 else 1.0
            heading = cog
        elif kind == "dwell":
            longitude = 0.0
            sog = 0.5
        elif kind == "loop":
            longitude, latitude = loop[index % len(loop)]
        elif kind == "missing":
            cog = None
            heading = None
        rows.append({"track_id": track_id, "base_date_time": origin + pd.Timedelta(seconds=offset), "longitude": longitude, "latitude": latitude, "sog": sog, "cog": cog, "heading": heading, "vessel_type": 70})
    return rows


def _synthetic_phase1() -> pd.DataFrame:
    regular = list(range(0, 1801, 180))
    rows: list[dict[str, object]] = []
    for name, kind in (("straight", "straight"), ("wrap", "wrap"), ("dwell", "dwell"), ("loop", "loop"), ("missing", "missing")):
        rows.extend(_rows(name, regular, kind))
    rows.extend(_rows("gap", regular, "straight"))
    rows.extend(_rows("gap", [2401 + value for value in regular], "straight"))
    rows.extend(_rows("duplicate", [0, 0, 180, 360, 540, 720, 900, 1080, 1260, 1440, 1800], "straight"))
    rows.extend(reversed(_rows("outoforder", regular, "straight")))
    rows.extend(_rows("onepoint", [0], "straight"))
    return pd.DataFrame(rows)


def _run_pipeline(frame: pd.DataFrame):
    config = load_feature_config(Path("config/trajectory_features_v1.json"))
    validated = validate_observations(frame)
    segmentation = segment_observations(validated.frame, config)
    windows = build_feature_windows(segmentation.observations, segmentation.segments, config)
    features = compute_window_features(segmentation.observations, windows, config)
    return validated.stats, segmentation.observations, segmentation.segments, windows, features


def test_cross_module_pipeline_is_deterministic_private_and_geospatially_sound(tmp_path) -> None:
    source = _synthetic_phase1()
    first = _run_pipeline(source)
    second = _run_pipeline(source)
    validation, segmented, segments, windows, features = first

    assert validation.input_out_of_order_pairs == 10
    assert len(segments) == 10
    assert len(windows) == 9
    assert windows["window_quality_status"].eq("sufficient").all()
    assert segments.loc[segments["track_id"] == "onepoint", "segment_quality_status"].item() == "insufficient_observations"
    for _, window in windows.iterrows():
        positions = window["_observation_positions"]
        members = segmented.iloc[list(positions)]
        assert members["segment_id"].nunique() == 1
        assert members["segment_id"].iloc[0] == window["segment_id"]

    assert list(features.columns[-len(FEATURE_COLUMNS):]) == list(FEATURE_COLUMNS)
    for public_frame in (segmented, segments, features):
        assert not {name.casefold() for name in public_frame.columns}.intersection(
            FORBIDDEN_PUBLIC_COLUMNS
        )
    missing_window = windows.loc[windows["track_id"] == "missing", "window_id"].item()
    missing = features.loc[features["window_id"] == missing_window].iloc[0]
    assert pd.isna(missing["course_change_abs_sum_deg"])
    assert pd.isna(missing["heading_cog_abs_median_deg"])
    assert str(features["window_start_utc"].dtype).endswith("UTC]")
    assert str(features["window_end_utc"].dtype).endswith("UTC]")

    for left, right in zip(first[1:], second[1:], strict=True):
        pd.testing.assert_frame_equal(left, right)

    destination = tmp_path / "features.parquet"
    write_feature_parquet(features, destination, {"seawatch_schema_version": "trajectory-features-v1", "seawatch_source_artifact_sha256": "a" * 64, "seawatch_source_manifest_sha256": "b" * 64, "seawatch_config_sha256": "c" * 64, "seawatch_generator_version": "phase2-v1", "seawatch_crs": "EPSG:4326", "seawatch_timezone": "UTC", "seawatch_feature_units": json.dumps(FEATURE_UNITS, sort_keys=True)})
    metadata = {key.decode(): value.decode() for key, value in pq.read_metadata(destination).metadata.items()}
    assert json.loads(metadata["seawatch_feature_units"]) == FEATURE_UNITS
