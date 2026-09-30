"""Build deterministic trajectory segments, windows, features, and QA metadata."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from apps.api.seawatch.adapters.noaa_ais import sha256_file
from apps.api.seawatch.trajectories.contracts import (
    load_feature_config,
    validate_observations,
)
from apps.api.seawatch.trajectories.feature_io import (
    build_feature_manifest,
    preflight_feature_outputs,
    read_phase1_parquet,
    render_feature_report,
    write_feature_parquet,
)
from apps.api.seawatch.trajectories.features import FEATURE_UNITS, compute_window_features
from apps.api.seawatch.trajectories.segmentation import segment_observations
from apps.api.seawatch.trajectories.windowing import build_feature_windows


DEFAULT_SOURCE = Path("data/processed/noaa_ais_2024-01-01_sf_bay.parquet")
DEFAULT_SOURCE_MANIFEST = Path("data/manifests/noaa_ais_2024-01-01_sf_bay.json")
DEFAULT_CONFIG = Path("config/trajectory_features_v1.json")
DEFAULT_SEGMENTED = Path(
    "data/processed/features/noaa_ais_2024-01-01_sf_bay_segmented.parquet"
)
DEFAULT_SEGMENTS = Path(
    "data/processed/features/noaa_ais_2024-01-01_sf_bay_segments.parquet"
)
DEFAULT_WINDOWS = Path(
    "data/processed/features/noaa_ais_2024-01-01_sf_bay_windows.parquet"
)
DEFAULT_MANIFEST = Path(
    "data/manifests/noaa_ais_2024-01-01_sf_bay_trajectory_features.json"
)
DEFAULT_REPORT = Path("docs/trajectory-feature-report.md")
GENERATOR_VERSION = "phase2-v1"


def _write_text(path: Path, text: str, *, overwrite: bool) -> None:
    path = Path(path)
    partial = path.with_name(path.name + ".partial")
    if path.exists() and not overwrite:
        raise FileExistsError(f"destination already exists: {path}")
    if partial.exists() and not overwrite:
        raise FileExistsError(f"partial output already exists: {partial}")
    if partial.exists():
        partial.unlink()
    path.parent.mkdir(parents=True, exist_ok=True)
    partial.write_text(text, encoding="utf-8")
    partial.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument(
        "--source-manifest", type=Path, default=DEFAULT_SOURCE_MANIFEST
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--segmented-output", type=Path, default=DEFAULT_SEGMENTED)
    parser.add_argument("--segments-output", type=Path, default=DEFAULT_SEGMENTS)
    parser.add_argument("--windows-output", type=Path, default=DEFAULT_WINDOWS)
    parser.add_argument("--manifest-output", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--report-output", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    output_paths = [
        args.segmented_output,
        args.segments_output,
        args.windows_output,
        args.manifest_output,
        args.report_output,
    ]
    try:
        preflight_feature_outputs(
            output_paths,
            overwrite=args.force,
            reserved_inputs=(args.source, args.source_manifest, args.config),
        )
        config = load_feature_config(args.config)
        source_manifest = json.loads(args.source_manifest.read_text(encoding="utf-8"))
        if not isinstance(source_manifest, dict):
            raise ValueError("source manifest must be a JSON object")
        source = read_phase1_parquet(args.source)
        validated = validate_observations(source)
        segmentation = segment_observations(validated.frame, config)
        private_windows = build_feature_windows(
            segmentation.observations, segmentation.segments, config
        )
        windows = compute_window_features(
            segmentation.observations, private_windows, config
        )
        source_sha256 = sha256_file(args.source)
        source_manifest_sha256 = sha256_file(args.source_manifest)
        config_sha256 = sha256_file(args.config)
        artifact_metadata = {
            "seawatch_schema_version": "trajectory-features-v1",
            "seawatch_crs": "EPSG:4326",
            "seawatch_timezone": "UTC",
            "seawatch_source_artifact_sha256": source_sha256,
            "seawatch_source_manifest_sha256": source_manifest_sha256,
            "seawatch_config_sha256": config_sha256,
            "seawatch_generator_version": GENERATOR_VERSION,
            "seawatch_feature_units": json.dumps(FEATURE_UNITS, sort_keys=True),
        }
        artifacts = {
            "segmented": write_feature_parquet(
                segmentation.observations,
                args.segmented_output,
                artifact_metadata,
                overwrite=args.force,
            ),
            "segments": write_feature_parquet(
                segmentation.segments,
                args.segments_output,
                artifact_metadata,
                overwrite=args.force,
            ),
            "windows": write_feature_parquet(
                windows,
                args.windows_output,
                artifact_metadata,
                overwrite=args.force,
            ),
        }
        manifest = build_feature_manifest(
            source_manifest=source_manifest,
            source_path=args.source,
            source_size_bytes=args.source.stat().st_size,
            source_sha256=source_sha256,
            source_manifest_path=args.source_manifest,
            source_manifest_sha256=source_manifest_sha256,
            config_path=args.config,
            config_sha256=config_sha256,
            config=config,
            validation_stats=validated.stats,
            observations=segmentation.observations,
            segments=segmentation.segments,
            windows=windows,
            artifacts=artifacts,
        )
        _write_text(
            args.manifest_output,
            json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n",
            overwrite=args.force,
        )
        _write_text(
            args.report_output,
            render_feature_report(manifest),
            overwrite=args.force,
        )
    except (FileExistsError, OSError, ValueError, json.JSONDecodeError) as error:
        parser.exit(1, f"error: {error}\n")

    print(f"segmented: {artifacts['segmented'].path} ({artifacts['segmented'].row_count} rows)")
    print(f"segments: {artifacts['segments'].path} ({artifacts['segments'].row_count} rows)")
    print(f"windows: {artifacts['windows'].path} ({artifacts['windows'].row_count} rows)")
    print(f"manifest: {args.manifest_output}")
    print(f"report: {args.report_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
