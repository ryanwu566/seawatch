"""Prepare the bounded NOAA AIS cargo-vessel smoke dataset."""

from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import sys

import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from apps.api.seawatch.adapters.noaa_ais import (
    ParquetInspection,
    inspect_parquet,
    read_download_record,
    sha256_file,
)
from apps.api.seawatch.trajectories.preprocess import (
    BoundingBox,
    build_manifest,
    prepare_smoke_dataset_batches,
    render_qa_report,
    write_geojson_preview,
    write_processed_parquet,
)


DEFAULT_SOURCE = Path("data/raw/ais-2024-01-01.parquet")
DEFAULT_PROCESSED = Path("data/processed/noaa_ais_2024-01-01_sf_bay.parquet")
DEFAULT_PREVIEW = Path("data/processed/noaa_ais_2024-01-01_sf_bay_preview.geojson")
DEFAULT_MANIFEST = Path("data/manifests/noaa_ais_2024-01-01_sf_bay.json")
DEFAULT_REPORT = Path("docs/data-foundation-report.md")
DEFAULT_COLUMN_MAP = Path("config/noaa_ais_2024_columns.json")
APPROVED_SOURCE_URL = (
    "https://ocmgeodatastor1.blob.core.windows.net/"
    "marinecadastre/ais2024/ais-2024-01-01.parquet"
)
DEFAULT_README_URL = "https://github.com/ocm-marinecadastre/ais-vessel-traffic/blob/main/data/ais-broadcast-points-2024-readme.md"
SF_BAY = BoundingBox(-122.55, 37.68, -122.25, 37.90)


def _write_text(path: Path, text: str, *, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(f"destination already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name + ".partial")
    partial.write_text(text, encoding="utf-8")
    partial.replace(path)


def preflight_output_paths(paths: list[Path], *, overwrite: bool) -> None:
    """Reject collisions before any expensive processing or artifact writes."""

    if overwrite:
        return
    collisions: list[Path] = []
    for raw_path in paths:
        path = Path(raw_path)
        partial = path.with_name(path.name + ".partial")
        collisions.extend(candidate for candidate in (path, partial) if candidate.exists())
    if collisions:
        rendered = ", ".join(str(path) for path in collisions)
        raise FileExistsError(f"output destination already exists: {rendered}")


def resolve_mapped_location_crs(
    inspection: ParquetInspection, column_map: dict[str, object]
) -> object:
    """Return the verified CRS for the exact mapped WKB Point column."""

    mapped_geometry = column_map.get("geometry")
    if mapped_geometry is None:
        raise ValueError(
            "coordinate-column mappings are not supported by the verified NOAA workflow; "
            "map the inspected GeoParquet geometry column"
        )
    geoparquet = inspection.geoparquet
    columns = geoparquet.get("columns") if isinstance(geoparquet, dict) else None
    details = columns.get(mapped_geometry) if isinstance(columns, dict) else None
    if not isinstance(details, dict):
        raise ValueError(
            f"mapped geometry column {mapped_geometry!r} has no GeoParquet metadata"
        )
    if str(details.get("encoding", "")).upper() != "WKB":
        raise ValueError(f"mapped geometry column {mapped_geometry!r} must use WKB encoding")
    geometry_types = details.get("geometry_types")
    if not isinstance(geometry_types, list) or not geometry_types:
        raise ValueError(f"mapped geometry column {mapped_geometry!r} must declare Point geometry")
    if any(str(value).lower() != "point" for value in geometry_types):
        raise ValueError(f"mapped geometry column {mapped_geometry!r} must contain only Point geometry")
    crs = details.get("crs")
    if crs is None:
        raise ValueError(f"mapped geometry column {mapped_geometry!r} does not declare a CRS")
    return crs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--download-record", type=Path)
    parser.add_argument("--column-map", type=Path, default=DEFAULT_COLUMN_MAP)
    parser.add_argument("--processed-output", type=Path, default=DEFAULT_PROCESSED)
    parser.add_argument("--preview-output", type=Path, default=DEFAULT_PREVIEW)
    parser.add_argument("--manifest-output", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--report-output", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--publisher", required=True)
    parser.add_argument("--observed-license", required=True)
    parser.add_argument("--license-url", required=True)
    parser.add_argument("--processing-version", default="phase1-v1")
    parser.add_argument("--max-observations", type=int, default=50_000)
    parser.add_argument("--preview-tracks", type=int, default=5)
    parser.add_argument("--batch-size", type=int, default=250_000)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    try:
        preflight_output_paths(
            [
                args.processed_output,
                args.preview_output,
                args.manifest_output,
                args.report_output,
            ],
            overwrite=args.force,
        )
    except FileExistsError as error:
        parser.exit(1, f"error: {error}\n")

    record_path = args.download_record or args.source.with_name(
        args.source.name + ".download.json"
    )
    record = read_download_record(record_path)
    if record.source_url != APPROVED_SOURCE_URL:
        parser.exit(1, "error: download record URL is not the approved NOAA 2024-01-01 source\n")
    if args.source.stat().st_size != record.content_length:
        parser.exit(1, "error: source size does not match the download record\n")
    if sha256_file(args.source) != record.sha256:
        parser.exit(1, "error: source SHA-256 does not match the download record\n")
    inspection = inspect_parquet(args.source)
    column_map = json.loads(args.column_map.read_text(encoding="utf-8"))
    if not isinstance(column_map, dict):
        parser.exit(1, "error: column map must be a JSON object\n")
    try:
        source_crs = resolve_mapped_location_crs(inspection, column_map)
    except ValueError as error:
        parser.exit(1, f"error: {error}\n")
    selected_columns = list(dict.fromkeys(str(value) for value in column_map.values()))
    parquet = pq.ParquetFile(args.source)
    frames = (
        batch.to_pandas()
        for batch in parquet.iter_batches(
            batch_size=args.batch_size, columns=selected_columns
        )
    )
    try:
        result = prepare_smoke_dataset_batches(
            frames,
            column_map,
            source_crs=source_crs,
            source_date=date(2024, 1, 1),
            bbox=SF_BAY,
            max_observations=args.max_observations,
            gap_threshold_minutes=10,
        )
        if result.filtered_rows == 0:
            parser.exit(2, "error: no cargo observations found in the approved bbox\n")
        processed = write_processed_parquet(
            result.frame, args.processed_output, overwrite=args.force
        )
        preview = write_geojson_preview(
            result.frame,
            args.preview_output,
            max_tracks=args.preview_tracks,
            overwrite=args.force,
        )
        manifest = build_manifest(
            result,
            dataset_id="noaa-ais-2024-01-01-sf-bay-cargo-smoke",
            publisher=args.publisher,
            source_url=record.source_url,
            source_readme_url=DEFAULT_README_URL,
            observed_license=args.observed_license,
            license_url=args.license_url,
            download_utc=record.download_utc,
            source_date=date(2024, 1, 1),
            content_length=record.content_length,
            source_sha256=record.sha256,
            source_inspection=inspection.to_dict(),
            bbox=SF_BAY,
            processing_version=args.processing_version,
            git_reference=args.processing_version,
            notes=[
                "San Francisco Bay is an engineering smoke-test area, not an official challenge region.",
                "AIS vessel type is self-reported and is not independently verified identity.",
            ],
        )
        _write_text(
            args.manifest_output,
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            overwrite=args.force,
        )
        report = render_qa_report(
            result,
            source_file_size=record.content_length,
            source_metadata_rows=inspection.row_count,
            processed_artifact=processed,
            geojson_artifact=preview,
            bbox=SF_BAY,
        )
        _write_text(args.report_output, report, overwrite=args.force)
    except (FileExistsError, ValueError) as error:
        parser.exit(1, f"error: {error}\n")

    print(f"processed: {processed.path} ({processed.row_count} rows)")
    print(f"preview: {preview.path} ({preview.row_count} observations)")
    print(f"manifest: {args.manifest_output}")
    print(f"report: {args.report_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
