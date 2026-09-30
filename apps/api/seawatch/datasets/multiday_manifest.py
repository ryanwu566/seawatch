"""Validate date-isolated AIS lineages and publish aggregate Phase 3A metadata."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
import json
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow.parquet as pq

from apps.api.seawatch.adapters.noaa_ais import sha256_file
from apps.api.seawatch.trajectories.contracts import (
    FORBIDDEN_PUBLIC_COLUMNS,
    PHASE1_COLUMNS,
)
from apps.api.seawatch.trajectories.feature_io import (
    REQUIRED_PROVENANCE_KEYS,
    distribution_summary,
)
from apps.api.seawatch.trajectories.features import FEATURE_COLUMNS

from .source_catalog import ApprovedDailySource, Phase3ACatalog


SCHEMA_VERSION = "phase3a-multiday-v1"
CORE_FEATURES = (
    "sog_median_knots",
    "sog_p95_knots",
    "path_distance_m",
    "displacement_m",
)


@dataclass(frozen=True)
class DailyLineage:
    source_date: date
    split_role: str
    phase1_manifest_path: Path
    feature_manifest_path: Path
    phase1_manifest_sha256: str
    feature_manifest_sha256: str
    column_map_sha256: str
    phase1_manifest: Mapping[str, object]
    feature_manifest: Mapping[str, object]
    source_artifact: Mapping[str, object]
    feature_artifacts: Mapping[str, Mapping[str, object]]
    qa: Mapping[str, object]


def _load_object(path: Path, label: str) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object")
    return payload


def _resolve(root: Path, raw_path: object) -> Path:
    path = Path(str(raw_path))
    return path if path.is_absolute() else Path(root) / path


def _portable_path(root: Path, path: Path) -> Path:
    try:
        return path.resolve().relative_to(root.resolve())
    except ValueError:
        return path


def _require_equal(actual: object, expected: object, label: str) -> None:
    if actual != expected:
        raise ValueError(f"{label} mismatch: expected {expected!r}, observed {actual!r}")


def _validate_public_columns(columns: Sequence[str], label: str) -> None:
    normalized = {str(value).casefold() for value in columns}
    exposed = sorted(normalized.intersection(FORBIDDEN_PUBLIC_COLUMNS))
    if exposed:
        raise ValueError(f"{label} contains forbidden public identifiers: {exposed}")


def _validate_date_columns(frame: pd.DataFrame, source_date: date, label: str) -> None:
    day_start = pd.Timestamp(source_date, tz="UTC")
    day_end = day_start + pd.Timedelta(days=1)
    timestamp_columns = [
        name
        for name in frame.columns
        if name == "base_date_time" or str(name).endswith("_utc")
    ]
    for name in timestamp_columns:
        values = pd.to_datetime(frame[name], errors="coerce", utc=True).dropna()
        if len(values) and (values.min() < day_start or values.max() >= day_end):
            raise ValueError(
                f"{label} timestamp column {name} is outside source date "
                f"{source_date.isoformat()}"
            )


def _validate_recorded_artifact(
    record: Mapping[str, object],
    *,
    root: Path,
    label: str,
    source_date: date,
    expected_metadata: Mapping[str, str] | None = None,
) -> tuple[Path, pd.DataFrame, dict[str, object]]:
    for key in ("path", "size_bytes", "sha256"):
        if key not in record:
            raise ValueError(f"{label} record is missing {key}")
    path = _resolve(root, record["path"])
    if not path.is_file():
        raise ValueError(f"{label} artifact is missing: {path}")
    _require_equal(path.stat().st_size, int(record["size_bytes"]), f"{label} size")
    _require_equal(sha256_file(path), record["sha256"], f"{label} hash")
    parquet = pq.ParquetFile(path)
    if "row_count" in record:
        _require_equal(
            parquet.metadata.num_rows, int(record["row_count"]), f"{label} row count"
        )
    columns = tuple(parquet.schema_arrow.names)
    _validate_public_columns(columns, label)
    metadata = {
        key.decode(): value.decode()
        for key, value in (parquet.schema_arrow.metadata or {}).items()
    }
    if expected_metadata is not None:
        missing = sorted(REQUIRED_PROVENANCE_KEYS.difference(metadata))
        if missing:
            raise ValueError(f"{label} metadata missing: {', '.join(missing)}")
        for key, expected in expected_metadata.items():
            _require_equal(metadata.get(key), expected, f"{label} metadata {key}")
    frame = parquet.read().to_pandas()
    _validate_date_columns(frame, source_date, label)
    return path, frame, {
        "path": str(record["path"]),
        "size_bytes": path.stat().st_size,
        "row_count": parquet.metadata.num_rows,
        "sha256": sha256_file(path),
    }


def _zero_inclusive_counts(
    member_ids: pd.Series, windows: pd.DataFrame, key: str
) -> dict[str, float | int | None]:
    if key in windows:
        counts = windows.groupby(key).size().reindex(member_ids, fill_value=0)
    else:
        counts = pd.Series(0, index=member_ids)
    return distribution_summary(counts)


def load_daily_lineage(
    entry: ApprovedDailySource,
    phase1_manifest_path: Path,
    feature_manifest_path: Path,
    *,
    root: Path,
) -> DailyLineage:
    """Load and validate one complete daily Phase 1/2 lineage."""

    root = Path(root)
    phase1_manifest_path = Path(phase1_manifest_path)
    feature_manifest_path = Path(feature_manifest_path)
    if not phase1_manifest_path.is_file() or not feature_manifest_path.is_file():
        raise ValueError("daily lineage manifest is missing")
    phase1 = _load_object(phase1_manifest_path, "Phase 1 manifest")
    features = _load_object(feature_manifest_path, "feature manifest")
    rendered = entry.date.isoformat()
    _require_equal(phase1.get("source_date"), rendered, "Phase 1 source date")
    _require_equal(phase1.get("source_url"), entry.source_url, "Phase 1 source URL")
    _require_equal(phase1.get("crs"), "EPSG:4326", "Phase 1 CRS")
    _require_equal(phase1.get("timezone"), "UTC", "Phase 1 timezone")
    _require_equal(phase1.get("observed_license"), "CC0 1.0 Universal", "license")
    _require_equal(tuple(phase1.get("output_columns", ())), PHASE1_COLUMNS, "Phase 1 schema")
    _validate_public_columns(tuple(phase1.get("output_columns", ())), "Phase 1 schema")
    _require_equal(features.get("schema_version"), "trajectory-features-v1", "feature schema")
    _require_equal(features.get("source_date"), rendered, "feature source date")
    _require_equal(
        features.get("source_dataset_id"), phase1.get("dataset_id"), "source dataset"
    )
    _require_equal(tuple(features.get("feature_columns", ())), FEATURE_COLUMNS, "feature columns")

    source_manifest = features.get("source_manifest")
    source_artifact = features.get("source_artifact")
    configuration = features.get("configuration")
    artifact_records = features.get("artifacts")
    if not all(isinstance(value, dict) for value in (source_manifest, source_artifact, configuration, artifact_records)):
        raise ValueError("feature manifest lineage records must be objects")
    assert isinstance(source_manifest, dict)
    assert isinstance(source_artifact, dict)
    assert isinstance(configuration, dict)
    assert isinstance(artifact_records, dict)
    phase1_hash = sha256_file(phase1_manifest_path)
    _require_equal(source_manifest.get("sha256"), phase1_hash, "source manifest hash")
    recorded_phase1_manifest = _resolve(root, source_manifest.get("path"))
    _require_equal(
        recorded_phase1_manifest.resolve(),
        phase1_manifest_path.resolve(),
        "source manifest path",
    )
    source_path, observations, source_record = _validate_recorded_artifact(
        source_artifact,
        root=root,
        label="source artifact",
        source_date=entry.date,
    )
    _require_equal(tuple(observations.columns), PHASE1_COLUMNS, "source artifact schema")
    source_metadata = {
        key.decode(): value.decode()
        for key, value in (pq.read_schema(source_path).metadata or {}).items()
    }
    _require_equal(source_metadata.get("seawatch_crs"), "EPSG:4326", "source artifact CRS")
    _require_equal(source_metadata.get("seawatch_timezone"), "UTC", "source artifact timezone")
    _require_equal(len(observations), int(phase1.get("output_rows", -1)), "Phase 1 output rows")
    _require_equal(len(observations), int(features.get("input_rows", -1)), "feature input rows")
    _require_equal(
        observations["track_id"].nunique(),
        int(features.get("input_track_count", -1)),
        "feature input tracks",
    )

    config_hash = str(configuration.get("sha256"))
    expected_metadata = {
        "seawatch_schema_version": "trajectory-features-v1",
        "seawatch_crs": "EPSG:4326",
        "seawatch_timezone": "UTC",
        "seawatch_source_artifact_sha256": str(source_artifact.get("sha256")),
        "seawatch_source_manifest_sha256": phase1_hash,
        "seawatch_config_sha256": config_hash,
        "seawatch_generator_version": "phase2-v1",
    }
    artifact_frames: dict[str, pd.DataFrame] = {}
    clean_records: dict[str, Mapping[str, object]] = {}
    for name in ("segmented", "segments", "windows"):
        record = artifact_records.get(name)
        if not isinstance(record, dict):
            raise ValueError(f"feature artifact record {name} is missing")
        _, frame, clean_record = _validate_recorded_artifact(
            record,
            root=root,
            label=name,
            source_date=entry.date,
            expected_metadata=expected_metadata,
        )
        artifact_frames[name] = frame
        clean_records[name] = clean_record
    segments = artifact_frames["segments"]
    windows = artifact_frames["windows"]
    _require_equal(len(segments), int(features.get("segment_count", -1)), "segment count")
    _require_equal(len(windows), int(features.get("candidate_window_count", -1)), "window count")
    accepted = (
        windows["window_quality_status"].eq("sufficient")
        if "window_quality_status" in windows
        else pd.Series(False, index=windows.index)
    )
    _require_equal(int(accepted.sum()), int(features.get("accepted_window_count", -1)), "accepted windows")
    _require_equal(int((~accepted).sum()), int(features.get("rejected_window_count", -1)), "rejected windows")
    accepted_by_track = windows.loc[accepted].groupby("track_id").size() if len(windows) else pd.Series(dtype="int64")
    accepted_count = int(accepted.sum())
    max_share = float(accepted_by_track.max() / accepted_count) if accepted_count else None
    values = configuration.get("values")
    if not isinstance(values, dict):
        raise ValueError("feature configuration values must be an object")
    duration = float(values.get("window_duration_seconds", 0))
    stride = float(values.get("window_stride_seconds", 0))
    if duration <= 0 or stride <= 0:
        raise ValueError("feature window duration and stride must be positive")
    overlap_factor = duration / stride
    qa = {
        "observations": len(observations),
        "tracks": int(observations["track_id"].nunique()),
        "segments": len(segments),
        "candidate_windows": len(windows),
        "accepted_windows": accepted_count,
        "rejected_windows": int((~accepted).sum()),
        "rejection_reasons": features.get("rejection_reasons", {}),
        "feature_missingness": features.get("feature_missingness", {}),
        "distributions": {
            **dict(features.get("distributions", {})),
            "windows_per_track": _zero_inclusive_counts(
                observations["track_id"].drop_duplicates(), windows, "track_id"
            ),
            "windows_per_segment": _zero_inclusive_counts(
                segments["segment_id"], windows, "segment_id"
            ),
        },
        "validation": features.get("validation", {}),
        "maximum_accepted_window_track_share": max_share,
        "nominal_overlap_factor": overlap_factor,
        "approximate_non_overlapping_windows": int(accepted_count // overlap_factor),
    }
    return DailyLineage(
        source_date=entry.date,
        split_role=entry.split_role,
        phase1_manifest_path=_portable_path(root, phase1_manifest_path),
        feature_manifest_path=_portable_path(root, feature_manifest_path),
        phase1_manifest_sha256=phase1_hash,
        feature_manifest_sha256=sha256_file(feature_manifest_path),
        column_map_sha256=sha256_file(root / "config/noaa_ais_2024_columns.json"),
        phase1_manifest=phase1,
        feature_manifest=features,
        source_artifact=source_record,
        feature_artifacts=clean_records,
        qa=qa,
    )


def _readiness(dates: list[dict[str, object]]) -> dict[str, object]:
    failures: list[str] = []
    for item in dates:
        rendered = str(item["source_date"])
        qa = item["qa"]
        assert isinstance(qa, dict)
        if int(qa["tracks"]) < 10:
            failures.append(f"{rendered} has fewer than 10 tracks")
        if int(qa["approximate_non_overlapping_windows"]) < 100:
            failures.append(f"{rendered} has fewer than 100 approximate non-overlapping windows")
        share = qa["maximum_accepted_window_track_share"]
        if share is None or float(share) > 0.20:
            failures.append(f"{rendered} exceeds or cannot measure the 20% single-track window share")
        missingness = qa["feature_missingness"]
        assert isinstance(missingness, dict)
        for feature in CORE_FEATURES:
            details = missingness.get(feature)
            rate = details.get("missing_rate") if isinstance(details, dict) else None
            if rate is None or float(rate) > 0.20:
                failures.append(f"{rendered} {feature} missingness exceeds 20% or is unmeasured")
    decision = (
        "A. DATA SUFFICIENT FOR BASELINE ANOMALY EXPERIMENTS"
        if not failures
        else "B. NEED ADDITIONAL DATA INVESTIGATION"
    )
    return {"decision": decision, "failed_criteria": failures}


def build_phase3a_manifest(
    catalog: Phase3ACatalog, lineages: Sequence[DailyLineage]
) -> dict[str, object]:
    """Build the fixed three-date aggregate contract without merging row data."""

    by_date: dict[date, DailyLineage] = {}
    for lineage in lineages:
        if lineage.source_date in by_date:
            raise ValueError(f"duplicate daily lineage for {lineage.source_date}")
        by_date[lineage.source_date] = lineage
    expected_dates = [entry.date for entry in catalog.entries]
    if sorted(by_date) != expected_dates:
        raise ValueError("daily lineages must contain exactly the approved catalog dates")
    ordered = [by_date[source_date] for source_date in expected_dates]
    for entry, lineage in zip(catalog.entries, ordered, strict=True):
        _require_equal(lineage.split_role, entry.split_role, "split role")
    config_hashes = {
        str(lineage.feature_manifest["configuration"]["sha256"])  # type: ignore[index]
        for lineage in ordered
    }
    if len(config_hashes) != 1:
        raise ValueError("feature configuration hash differs across dates")
    config_values = [lineage.feature_manifest["configuration"]["values"] for lineage in ordered]  # type: ignore[index]
    if any(value != config_values[0] for value in config_values[1:]):
        raise ValueError("feature configuration values differ across dates")
    comparison_fields = (
        "publisher", "observed_license", "crs", "timezone", "geographic_bbox",
        "vessel_type_filter", "source_columns", "output_columns", "processing_version",
    )
    for field in comparison_fields:
        values = [lineage.phase1_manifest.get(field) for lineage in ordered]
        if any(value != values[0] for value in values[1:]):
            raise ValueError(f"Phase 1 {field} differs across dates")
    column_map_hashes = {lineage.column_map_sha256 for lineage in ordered}
    if len(column_map_hashes) != 1:
        raise ValueError("Phase 1 column mapping hash differs across dates")

    date_records: list[dict[str, object]] = []
    for lineage in ordered:
        date_records.append(
            {
                "source_date": lineage.source_date.isoformat(),
                "split_role": lineage.split_role,
                "phase1_manifest": {
                    "path": str(lineage.phase1_manifest_path),
                    "sha256": lineage.phase1_manifest_sha256,
                },
                "feature_manifest": {
                    "path": str(lineage.feature_manifest_path),
                    "sha256": lineage.feature_manifest_sha256,
                },
                "source_artifact": dict(lineage.source_artifact),
                "feature_artifacts": {
                    name: dict(record)
                    for name, record in lineage.feature_artifacts.items()
                },
                "qa": dict(lineage.qa),
            }
        )
    totals = {
        name: sum(int(item["qa"][name]) for item in date_records)  # type: ignore[index]
        for name in (
            "observations", "tracks", "segments", "candidate_windows",
            "accepted_windows", "rejected_windows",
        )
    }
    readiness = _readiness(date_records)
    return {
        "schema_version": SCHEMA_VERSION,
        "cohort_id": "noaa-ais-2024-01-01-to-2024-01-03-sf-bay-phase3a",
        "dates": date_records,
        "totals": totals,
        "shared_contract": {
            "column_map_path": "config/noaa_ais_2024_columns.json",
            "column_map_sha256": next(iter(column_map_hashes)),
            "feature_config_path": "config/trajectory_features_v1.json",
            "feature_config_sha256": next(iter(config_hashes)),
            "feature_config_values": config_values[0],
            **{
                field: ordered[0].phase1_manifest.get(field)
                for field in comparison_fields
                if field != "source_columns"
            },
            "feature_schema_version": "trajectory-features-v1",
            "feature_columns": list(FEATURE_COLUMNS),
        },
        "comparability": {"passed": True, "failed_checks": []},
        "phase3b_readiness": readiness,
        "notes": [
            "Dates are processed independently; no merged observation or feature dataset exists.",
            "Overlapping windows share observations and are not independent samples.",
            "Date-scoped track surrogates are display controls, not anonymization.",
            "Movement distributions are descriptive data QA and are not anomaly labels.",
        ],
    }


def _format(value: object) -> str:
    if value is None:
        return "not measured"
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


def render_phase3a_report(manifest: Mapping[str, object]) -> str:
    """Render a compact measured cross-date QA and readiness report."""

    dates = manifest["dates"]
    assert isinstance(dates, list)
    rows = []
    for item in dates:
        qa = item["qa"]
        rows.append(
            "| " + " | ".join(
                _format(value)
                for value in (
                    item["source_date"], item["split_role"], qa["observations"],
                    qa["tracks"], qa["segments"], qa["candidate_windows"],
                    qa["accepted_windows"], qa["rejected_windows"],
                    qa["approximate_non_overlapping_windows"],
                    qa["maximum_accepted_window_track_share"],
                )
            ) + " |"
        )
    readiness = manifest["phase3b_readiness"]
    assert isinstance(readiness, dict)
    failures = readiness["failed_criteria"]
    failure_text = (
        "\n".join(f"- {value}" for value in failures)
        if failures
        else "- All Phase 3B readiness criteria passed."
    )
    feature_names = tuple(FEATURE_COLUMNS)
    missing_rows = []
    for feature in feature_names:
        rates = []
        for item in dates:
            details = item["qa"]["feature_missingness"].get(feature, {})
            rate = details.get("missing_rate") if isinstance(details, dict) else None
            rates.append("not measured" if rate is None else f"{float(rate):.4%}")
        missing_rows.append(f"| `{feature}` | " + " | ".join(rates) + " |")
    distribution_names = (
        "input_sog_knots",
        "path_distance_m",
        "displacement_m",
        "path_displacement_ratio",
        "course_change_abs_sum_deg",
        "course_change_abs_p95_deg",
        "low_speed_fraction",
        "max_gap_seconds",
    )
    distribution_rows = []
    for name in distribution_names:
        for item in dates:
            values = item["qa"]["distributions"].get(name, {})
            distribution_rows.append(
                f"| `{name}` | {item['source_date']} | "
                + " | ".join(
                    _format(values.get(metric) if isinstance(values, dict) else None)
                    for metric in ("minimum", "p25", "median", "p75", "p95", "maximum")
                )
                + " |"
            )
    quality_rows = []
    for item in dates:
        qa = item["qa"]
        validation = qa.get("validation", {})
        distributions = qa.get("distributions", {})
        windows_per_track = distributions.get("windows_per_track", {})
        quality_rows.append(
            f"| {item['source_date']} | {validation.get('input_out_of_order_pairs', 'not measured')} | "
            f"{validation.get('invalid_sog_rows', 'not measured')} | "
            f"{validation.get('invalid_cog_rows', 'not measured')} | "
            f"{validation.get('invalid_heading_rows', 'not measured')} | "
            f"{json.dumps(qa.get('rejection_reasons', {}), sort_keys=True)} | "
            f"{_format(windows_per_track.get('minimum'))} | "
            f"{_format(windows_per_track.get('median'))} | "
            f"{_format(windows_per_track.get('maximum'))} |"
        )
    return (
        "# Phase 3A NOAA AIS Data Expansion Report\n\n"
        "The three dates were processed independently with fixed roles. Counts and "
        "movement summaries are descriptive QA, not anomaly scores.\n\n"
        "## Daily cohort\n\n"
        "| Date | Role | Observations | Tracks | Segments | Candidate windows | Accepted | Rejected | Approx. non-overlap | Max track share |\n"
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|\n"
        + "\n".join(rows)
        + "\n\n## Feature missingness\n\n"
        "| Feature | 2024-01-01 | 2024-01-02 | 2024-01-03 |\n"
        "|---|---:|---:|---:|\n"
        + "\n".join(missing_rows)
        + "\n\n## SOG, path, turning, and quality distributions\n\n"
        "| Distribution | Date | Min | P25 | Median | P75 | P95 | Max |\n"
        "|---|---|---:|---:|---:|---:|---:|---:|\n"
        + "\n".join(distribution_rows)
        + "\n\nNull distribution values mean the feature was unsupported, not zero. "
        "Angular and path/displacement-ratio support remains sparse and must not be zero-filled.\n\n"
        "## Data-quality comparison\n\n"
        "| Date | Out-of-order pairs | Invalid SOG | Invalid COG | Invalid heading | Rejections | Windows/track min | median | max |\n"
        "|---|---:|---:|---:|---:|---|---:|---:|---:|\n"
        + "\n".join(quality_rows)
        + "\n\n## Phase 3B readiness\n\n"
        + str(readiness["decision"])
        + "\n\n"
        + failure_text
        + "\n\nOverlapping windows are dependent, and date-scoped track surrogates do not provide anonymization.\n"
    )
