"""Parquet contracts and atomic artifact writing for trajectory features."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import asdict
import math
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from apps.api.seawatch.adapters.noaa_ais import sha256_file

from .contracts import (
    FeatureConfig,
    PHASE1_COLUMNS,
    ValidationStats,
    assert_public_feature_schema,
)
from .features import FEATURE_COLUMNS
from .preprocess import ArtifactRecord


REQUIRED_PROVENANCE_KEYS = frozenset(
    {
        "seawatch_schema_version",
        "seawatch_crs",
        "seawatch_timezone",
        "seawatch_source_artifact_sha256",
        "seawatch_source_manifest_sha256",
        "seawatch_config_sha256",
        "seawatch_generator_version",
        "seawatch_feature_units",
    }
)


def read_phase1_parquet(path: Path) -> pd.DataFrame:
    """Read the exact Phase 1 public observation contract."""

    path = Path(path)
    parquet = pq.ParquetFile(path)
    schema = parquet.schema_arrow
    metadata = schema.metadata or {}
    if b"seawatch_crs" not in metadata:
        raise ValueError("Phase 1 Parquet is missing seawatch_crs metadata")
    if metadata[b"seawatch_crs"].decode() != "EPSG:4326":
        raise ValueError("Phase 1 Parquet CRS must be EPSG:4326")
    if b"seawatch_timezone" not in metadata:
        raise ValueError("Phase 1 Parquet is missing seawatch_timezone metadata")
    if metadata[b"seawatch_timezone"].decode() != "UTC":
        raise ValueError("Phase 1 Parquet timezone must be UTC")
    actual = tuple(schema.names)
    if actual != PHASE1_COLUMNS:
        missing = sorted(set(PHASE1_COLUMNS).difference(actual))
        unexpected = sorted(set(actual).difference(PHASE1_COLUMNS))
        details = []
        if missing:
            details.append(f"missing: {', '.join(missing)}")
        if unexpected:
            details.append(f"unexpected: {', '.join(unexpected)}")
        if not details:
            details.append("column order differs")
        raise ValueError(f"Phase 1 Parquet schema mismatch ({'; '.join(details)})")
    frame = parquet.read().to_pandas()
    frame["base_date_time"] = pd.to_datetime(
        frame["base_date_time"], errors="raise", utc=True
    )
    return frame


def preflight_feature_outputs(
    paths: Iterable[Path], *, overwrite: bool, reserved_inputs: Iterable[Path] = ()
) -> None:
    """Reject every destination collision before pipeline computation begins."""

    paths = [Path(path) for path in paths]
    write_paths = [
        candidate
        for path in paths
        for candidate in (path, path.with_name(path.name + ".partial"))
    ]
    resolved = [str(path.resolve()).casefold() for path in write_paths]
    if len(resolved) != len(set(resolved)):
        raise ValueError("duplicate feature output or partial paths are not allowed")
    reserved = {str(Path(path).resolve()).casefold() for path in reserved_inputs}
    if reserved.intersection(resolved):
        raise ValueError("feature output path aliases an input path")
    if overwrite:
        return
    collisions: list[Path] = []
    collisions.extend(path for path in write_paths if path.exists())
    if collisions:
        rendered = ", ".join(str(path) for path in collisions)
        raise FileExistsError(f"feature output destination already exists: {rendered}")


def write_feature_parquet(
    frame: pd.DataFrame,
    path: Path,
    metadata: Mapping[str, str],
    *,
    overwrite: bool = False,
) -> ArtifactRecord:
    """Write a public-safe feature table atomically with required provenance."""

    assert_public_feature_schema(frame.columns)
    missing_metadata = sorted(REQUIRED_PROVENANCE_KEYS.difference(metadata))
    if missing_metadata:
        raise ValueError(
            f"missing feature artifact metadata: {', '.join(missing_metadata)}"
        )
    path = Path(path)
    partial = path.with_name(path.name + ".partial")
    if path.exists() and not overwrite:
        raise FileExistsError(f"destination already exists: {path}")
    if partial.exists() and not overwrite:
        raise FileExistsError(f"partial output already exists: {partial}")
    if partial.exists():
        partial.unlink()
    path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pandas(frame, preserve_index=False)
    schema_metadata = dict(table.schema.metadata or {})
    schema_metadata.update(
        {str(key).encode(): str(value).encode() for key, value in metadata.items()}
    )
    pq.write_table(table.replace_schema_metadata(schema_metadata), partial)
    partial.replace(path)
    return ArtifactRecord(
        path=path,
        size_bytes=path.stat().st_size,
        row_count=len(frame),
        sha256=sha256_file(path),
    )


def _finite_or_none(value: object) -> float | int | None:
    if value is None or pd.isna(value):
        return None
    numeric = float(value)
    return numeric if math.isfinite(numeric) else None


def distribution_summary(values: pd.Series) -> dict[str, float | int | None]:
    numeric = pd.to_numeric(values, errors="coerce")
    present = numeric.dropna()
    count = int(len(numeric))
    missing = int(numeric.isna().sum())
    if present.empty:
        metrics = {name: None for name in ("minimum", "p25", "median", "p75", "p95", "maximum")}
    else:
        metrics = {
            "minimum": _finite_or_none(present.min()),
            "p25": _finite_or_none(present.quantile(0.25)),
            "median": _finite_or_none(present.median()),
            "p75": _finite_or_none(present.quantile(0.75)),
            "p95": _finite_or_none(present.quantile(0.95)),
            "maximum": _finite_or_none(present.max()),
        }
    return {
        "count": count,
        "missing_count": missing,
        "missing_rate": missing / count if count else None,
        **metrics,
    }


def _artifact_payload(record: ArtifactRecord) -> dict[str, object]:
    return {
        "path": str(record.path),
        "size_bytes": record.size_bytes,
        "row_count": record.row_count,
        "sha256": record.sha256,
    }


def build_feature_manifest(
    *,
    source_manifest: Mapping[str, object],
    source_path: Path,
    source_size_bytes: int,
    source_sha256: str,
    source_manifest_path: Path,
    source_manifest_sha256: str,
    config_path: Path,
    config_sha256: str,
    config: FeatureConfig,
    validation_stats: ValidationStats,
    observations: pd.DataFrame,
    segments: pd.DataFrame,
    windows: pd.DataFrame,
    artifacts: Mapping[str, ArtifactRecord],
) -> dict[str, object]:
    """Build aggregate-only, machine-readable Phase 2 QA metadata."""

    accepted = windows["window_quality_status"].eq("sufficient")
    rejection_reasons = {
        str(name): int(value)
        for name, value in windows.loc[~accepted, "window_quality_status"]
        .value_counts()
        .sort_index()
        .items()
    }
    feature_missingness = {
        name: {
            "missing_count": int(windows[name].isna().sum()),
            "missing_rate": float(windows[name].isna().mean()) if len(windows) else None,
        }
        for name in FEATURE_COLUMNS
    }
    windows_per_track = windows.groupby("track_id").size().reindex(
        observations["track_id"].drop_duplicates(), fill_value=0
    )
    windows_per_segment = windows.groupby("segment_id").size().reindex(
        segments["segment_id"], fill_value=0
    )
    segments_per_track = segments.groupby("track_id").size()
    distributions = {
        "segments_per_track": distribution_summary(segments_per_track),
        "segment_duration_seconds": distribution_summary(segments["segment_duration_seconds"]),
        "observations_per_segment": distribution_summary(segments["observation_count"]),
        "windows_per_track": distribution_summary(windows_per_track),
        "windows_per_segment": distribution_summary(windows_per_segment),
        "max_gap_seconds": distribution_summary(windows["max_gap_seconds"]),
        "input_sog_knots": distribution_summary(observations["sog"]),
        "course_change_abs_sum_deg": distribution_summary(windows["course_change_abs_sum_deg"]),
        "course_change_abs_p95_deg": distribution_summary(windows["course_change_abs_p95_deg"]),
        "path_distance_m": distribution_summary(windows["path_distance_m"]),
        "displacement_m": distribution_summary(windows["displacement_m"]),
        "path_displacement_ratio": distribution_summary(windows["path_displacement_ratio"]),
        "low_speed_fraction": distribution_summary(windows["low_speed_fraction"]),
        "low_speed_duration_seconds": distribution_summary(windows["low_speed_duration_seconds"]),
    }
    return {
        "schema_version": "trajectory-features-v1",
        "dataset_id": f"{source_manifest.get('dataset_id', 'phase1-observations')}-trajectory-features",
        "source_dataset_id": source_manifest.get("dataset_id"),
        "source_date": source_manifest.get("source_date"),
        "source_artifact": {
            "path": str(source_path),
            "size_bytes": source_size_bytes,
            "sha256": source_sha256,
        },
        "source_manifest": {
            "path": str(source_manifest_path),
            "sha256": source_manifest_sha256,
        },
        "configuration": {
            "path": str(config_path),
            "sha256": config_sha256,
            "values": asdict(config),
        },
        "input_rows": len(observations),
        "input_track_count": int(observations["track_id"].nunique()),
        "validation": asdict(validation_stats),
        "segmentation_rule": (
            "new segment when UTC gap is strictly greater than "
            f"{config.segment_gap_seconds:g} seconds"
        ),
        "segment_count": len(segments),
        "window_rule": (
            f"{config.window_duration_seconds:g}-second half-open windows, "
            f"{config.window_stride_seconds:g}-second stride, anchored per segment"
        ),
        "candidate_window_count": len(windows),
        "accepted_window_count": int(accepted.sum()),
        "rejected_window_count": int((~accepted).sum()),
        "rejection_reasons": rejection_reasons,
        "feature_columns": list(FEATURE_COLUMNS),
        "feature_missingness": feature_missingness,
        "distributions": distributions,
        "artifacts": {name: _artifact_payload(record) for name, record in artifacts.items()},
        "phase3_gate": "B. EXPAND DATA BEFORE MODELING",
        "minimum_recommended_expansion": (
            "Acquire at least two additional separately approved dates as independent "
            "calibration and test partitions, then reassess vessel diversity and feature coverage."
        ),
        "notes": [
            "Quality metadata is not behavioral evidence.",
            "Overlapping windows share observations and are not independent samples.",
            "The deterministic track surrogate is a display control, not anonymization.",
            "Statistical extremes are not labeled as anomalies.",
        ],
    }


def render_feature_report(manifest: Mapping[str, object]) -> str:
    """Render the aggregate manifest as a measured Markdown QA report."""

    overview = [
        ("Input observations", manifest["input_rows"]),
        ("Input tracks", manifest["input_track_count"]),
        ("Segments", manifest["segment_count"]),
        ("Candidate windows", manifest["candidate_window_count"]),
        ("Accepted windows", manifest["accepted_window_count"]),
        ("Rejected windows", manifest["rejected_window_count"]),
    ]
    overview_table = "\n".join(f"| {name} | {value} |" for name, value in overview)
    reasons = manifest["rejection_reasons"]
    reason_rows = (
        "\n".join(f"| {name} | {value} |" for name, value in reasons.items())
        if reasons
        else "| none | 0 |"
    )
    missingness = manifest["feature_missingness"]
    missing_rows = "\n".join(
        (
            f"| {name} | {values['missing_count']} | {values['missing_rate']:.4%} |"
            if values["missing_rate"] is not None
            else f"| {name} | {values['missing_count']} | not measured |"
        )
        for name, values in missingness.items()
    )
    distribution_sections: list[str] = []
    for name, values in manifest["distributions"].items():
        distribution_sections.append(
            f"### `{name}`\n\n"
            "| Count | Missing | Missing rate | Min | P25 | Median | P75 | P95 | Max |\n"
            "|---:|---:|---:|---:|---:|---:|---:|---:|---:|\n"
            f"| {values['count']} | {values['missing_count']} | "
            f"{values['missing_rate'] if values['missing_rate'] is not None else 'not measured'} | "
            f"{values['minimum']} | {values['p25']} | {values['median']} | "
            f"{values['p75']} | {values['p95']} | {values['maximum']} |"
        )
    planning_dataset_id = "noaa-ais-2024-01-01-sf-bay-cargo-smoke"
    if manifest["source_dataset_id"] != planning_dataset_id:
        reconciliation = (
            "The 3,216/2,829 planning comparison does not apply to source dataset "
            f"`{manifest['source_dataset_id']}`."
        )
    elif (
        manifest["candidate_window_count"] == 3216
        and manifest["accepted_window_count"] == 2829
    ):
        reconciliation = (
            "The implemented pipeline independently reproduced the planning values: "
            "3,216 candidate windows and 2,829 accepted windows. There is no count "
            "difference to explain or force; 387 windows were measured as rejected "
            "for insufficient observations."
        )
    else:
        reconciliation = (
            f"For the planning dataset, the implementation measured "
            f"{manifest['candidate_window_count']:,} candidates and "
            f"{manifest['accepted_window_count']:,} accepted windows, differing from "
            "3,216/2,829. The report does not infer a cause; the discrepancy must be "
            "investigated and documented rather than forced to match."
        )
    return (
        "# Trajectory Feature QA Report\n\n"
        "Measured from the existing Phase 1 processed observations. Values describe "
        "data quality and movement distributions; statistical extremes are not labels.\n\n"
        "## Counts\n\n| Metric | Value |\n|---|---:|\n"
        f"{overview_table}\n\n"
        "## Planning estimate reconciliation\n\n"
        f"{reconciliation}\n\n"
        "## Rejected windows by reason\n\n| Reason | Count |\n|---|---:|\n"
        f"{reason_rows}\n\n"
        "## Feature missingness\n\n| Feature | Missing | Rate |\n|---|---:|---:|\n"
        f"{missing_rows}\n\n"
        "## Distributions\n\n"
        + "\n\n".join(distribution_sections)
        + "\n\n## Phase 3 gate\n\n"
        + str(manifest["phase3_gate"])
        + "\n\n"
        + str(manifest["minimum_recommended_expansion"])
        + " The additional dates require separate approval and are not acquired in Phase 2.\n"
    )
