"""Deterministic AIS observation validation and preparation."""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Iterable, Mapping
from datetime import date, datetime
from hashlib import sha256
from pathlib import Path
import json

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from pyproj import CRS, Transformer
from pyproj.exceptions import CRSError
from shapely import from_wkb, get_type_id, get_x, get_y, is_empty, is_missing


@dataclass(frozen=True)
class BoundingBox:
    west: float
    south: float
    east: float
    north: float

    def __post_init__(self) -> None:
        if self.west > self.east or self.south > self.north:
            raise ValueError("bounding box minimums must not exceed maximums")


@dataclass(frozen=True)
class DuplicateStats:
    exact_duplicate_rows: int
    duplicate_timestamp_rows: int
    duplicate_timestamp_groups: int


@dataclass(frozen=True)
class TimeGapStats:
    observation_pairs: int
    positive_gap_count: int
    zero_gap_count: int
    negative_gap_count: int
    gaps_over_threshold_count: int
    minimum_positive_seconds: float | None
    median_positive_seconds: float | None
    maximum_positive_seconds: float | None
    threshold_seconds: float


@dataclass(frozen=True)
class SelectionStats:
    input_rows: int
    selected_rows: int
    input_tracks: int
    selected_tracks: int
    max_observations: int
    skipped_track_ids: tuple[str, ...]
    oversized_track_ids: tuple[str, ...]


@dataclass(frozen=True)
class ArtifactRecord:
    path: Path
    size_bytes: int
    row_count: int
    sha256: str


@dataclass(frozen=True)
class ProcessingResult:
    frame: pd.DataFrame
    source_rows: int
    invalid_coordinate_rows: int
    invalid_timestamp_rows: int
    invalid_identifier_rows: int
    bbox_rows: int
    filtered_rows: int
    output_rows: int
    vessel_count: int
    duplicate_stats: DuplicateStats
    time_gap_stats: TimeGapStats
    selection_stats: SelectionStats
    source_columns: tuple[str, ...]
    output_columns: tuple[str, ...]
    missing_rates: dict[str, float]


def parse_utc_timestamps(values: pd.Series) -> pd.Series:
    """Parse mixed timestamp representations as timezone-aware UTC."""

    return pd.to_datetime(values, errors="coerce", utc=True, format="mixed")


def valid_coordinate_mask(longitude: pd.Series, latitude: pd.Series) -> pd.Series:
    lon = pd.to_numeric(longitude, errors="coerce")
    lat = pd.to_numeric(latitude, errors="coerce")
    return pd.Series(
        np.isfinite(lon)
        & np.isfinite(lat)
        & lon.between(-180.0, 180.0, inclusive="both")
        & lat.between(-90.0, 90.0, inclusive="both"),
        index=longitude.index,
        dtype=bool,
    )


def bbox_mask(
    longitude: pd.Series, latitude: pd.Series, bbox: BoundingBox
) -> pd.Series:
    valid = valid_coordinate_mask(longitude, latitude)
    lon = pd.to_numeric(longitude, errors="coerce")
    lat = pd.to_numeric(latitude, errors="coerce")
    return (
        valid
        & lon.between(bbox.west, bbox.east, inclusive="both")
        & lat.between(bbox.south, bbox.north, inclusive="both")
    )


def cargo_vessel_mask(vessel_type: pd.Series) -> pd.Series:
    values = pd.to_numeric(vessel_type, errors="coerce")
    return (
        values.notna()
        & values.between(70, 79, inclusive="both")
        & values.eq(np.floor(values))
    )


def surrogate_track_id(source_vessel_id: object, source_date: date) -> str:
    normalized = str(source_vessel_id).strip()
    if not normalized or normalized.lower() in {"none", "nan"}:
        raise ValueError("source vessel identifier must be non-null and non-empty")
    value = f"seawatch:noaa-ais:{source_date.isoformat()}:{normalized}"
    return sha256(value.encode("utf-8")).hexdigest()[:16]


def order_and_deduplicate(
    frame: pd.DataFrame,
) -> tuple[pd.DataFrame, DuplicateStats]:
    required = {"source_vessel_id", "base_date_time"}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"missing ordering columns: {', '.join(missing)}")

    working = frame.copy()
    working["_source_row_order"] = np.arange(len(working))
    comparison_columns = [
        name for name in working.columns if name != "_source_row_order"
    ]
    exact_mask = working.duplicated(subset=comparison_columns, keep="first")
    exact_duplicate_rows = int(exact_mask.sum())
    working = working.loc[~exact_mask].copy()
    working = working.sort_values(
        ["source_vessel_id", "base_date_time", "_source_row_order"],
        kind="mergesort",
    )
    timestamp_keys = ["source_vessel_id", "base_date_time"]
    duplicate_mask = working.duplicated(subset=timestamp_keys, keep=False)
    duplicate_timestamp_rows = int(duplicate_mask.sum())
    duplicate_timestamp_groups = int(
        (working.groupby(timestamp_keys, dropna=False).size() > 1).sum()
    )
    result = working.drop(columns="_source_row_order").reset_index(drop=True)
    return result, DuplicateStats(
        exact_duplicate_rows=exact_duplicate_rows,
        duplicate_timestamp_rows=duplicate_timestamp_rows,
        duplicate_timestamp_groups=duplicate_timestamp_groups,
    )


def summarize_time_gaps(
    frame: pd.DataFrame, *, threshold_minutes: float = 10
) -> TimeGapStats:
    required = {"source_vessel_id", "base_date_time"}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"missing time-gap columns: {', '.join(missing)}")
    threshold_seconds = float(threshold_minutes * 60)
    gap_seconds = (
        frame.groupby("source_vessel_id", sort=False)["base_date_time"]
        .diff()
        .dt.total_seconds()
        .dropna()
    )
    positive = gap_seconds[gap_seconds > 0]
    return TimeGapStats(
        observation_pairs=int(len(gap_seconds)),
        positive_gap_count=int((gap_seconds > 0).sum()),
        zero_gap_count=int((gap_seconds == 0).sum()),
        negative_gap_count=int((gap_seconds < 0).sum()),
        gaps_over_threshold_count=int((gap_seconds > threshold_seconds).sum()),
        minimum_positive_seconds=(float(positive.min()) if len(positive) else None),
        median_positive_seconds=(float(positive.median()) if len(positive) else None),
        maximum_positive_seconds=(float(positive.max()) if len(positive) else None),
        threshold_seconds=threshold_seconds,
    )


def select_complete_tracks(
    frame: pd.DataFrame, *, max_observations: int = 50_000
) -> tuple[pd.DataFrame, SelectionStats]:
    if max_observations <= 0:
        raise ValueError("max_observations must be positive")
    required = {"track_id", "base_date_time"}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"missing selection columns: {', '.join(missing)}")

    sizes = frame.groupby("track_id", sort=True).size()
    selected_ids: list[str] = []
    skipped_ids: list[str] = []
    oversized_ids: list[str] = []
    selected_rows = 0
    for raw_track_id, raw_size in sizes.items():
        track_id = str(raw_track_id)
        size = int(raw_size)
        if size > max_observations:
            skipped_ids.append(track_id)
            oversized_ids.append(track_id)
        elif selected_rows + size <= max_observations:
            selected_ids.append(track_id)
            selected_rows += size
        else:
            skipped_ids.append(track_id)

    selected = frame[frame["track_id"].astype(str).isin(selected_ids)].copy()
    selected = selected.sort_values(
        ["track_id", "base_date_time"], kind="mergesort"
    ).reset_index(drop=True)
    stats = SelectionStats(
        input_rows=int(len(frame)),
        selected_rows=int(len(selected)),
        input_tracks=int(len(sizes)),
        selected_tracks=int(len(selected_ids)),
        max_observations=max_observations,
        skipped_track_ids=tuple(skipped_ids),
        oversized_track_ids=tuple(oversized_ids),
    )
    return selected, stats


def prepare_smoke_dataset(
    frame: pd.DataFrame,
    column_map: Mapping[str, str],
    *,
    source_crs: object | None,
    source_date: date,
    bbox: BoundingBox,
    max_observations: int = 50_000,
    gap_threshold_minutes: float = 10,
) -> ProcessingResult:
    return prepare_smoke_dataset_batches(
        [frame],
        column_map,
        source_crs=source_crs,
        source_date=source_date,
        bbox=bbox,
        max_observations=max_observations,
        gap_threshold_minutes=gap_threshold_minutes,
    )


def prepare_smoke_dataset_batches(
    frames: Iterable[pd.DataFrame],
    column_map: Mapping[str, str],
    *,
    source_crs: object | None,
    source_date: date,
    bbox: BoundingBox,
    max_observations: int = 50_000,
    gap_threshold_minutes: float = 10,
) -> ProcessingResult:
    source_rows = 0
    invalid_coordinate_rows = 0
    invalid_timestamp_rows = 0
    invalid_identifier_rows = 0
    bbox_rows = 0
    filtered_rows = 0
    source_columns: tuple[str, ...] | None = None
    cargo_batches: list[pd.DataFrame] = []

    for frame in frames:
        current_columns = tuple(str(name) for name in frame.columns)
        if source_columns is None:
            source_columns = current_columns
        elif current_columns != source_columns:
            raise ValueError("all source batches must have the same columns and order")
        source_rows += len(frame)
        canonical = canonicalize_observations(
            frame, column_map, source_crs=source_crs
        )
        coordinate_valid = valid_coordinate_mask(
            canonical["longitude"], canonical["latitude"]
        )
        timestamp_valid = canonical["base_date_time"].notna()
        identifiers = canonical["source_vessel_id"]
        identifier_valid = identifiers.notna() & identifiers.ne("")
        invalid_coordinate_rows += int((~coordinate_valid).sum())
        invalid_timestamp_rows += int((~timestamp_valid).sum())
        invalid_identifier_rows += int((~identifier_valid).sum())
        eligible_for_bbox = canonical.loc[
            coordinate_valid & timestamp_valid & identifier_valid
        ].copy()
        in_bbox = bbox_mask(
            eligible_for_bbox["longitude"], eligible_for_bbox["latitude"], bbox
        )
        bounded = eligible_for_bbox.loc[in_bbox].copy()
        bbox_rows += len(bounded)
        if "vessel_type" not in bounded:
            raise ValueError("vessel_type is required for the cargo smoke dataset")
        cargo = bounded.loc[cargo_vessel_mask(bounded["vessel_type"])].copy()
        filtered_rows += len(cargo)
        cargo_batches.append(cargo)

    if source_columns is None:
        raise ValueError("at least one source batch is required")
    cargo_all = pd.concat(cargo_batches, ignore_index=True)
    ordered, duplicate_stats = order_and_deduplicate(cargo_all)
    time_gap_stats = summarize_time_gaps(
        ordered, threshold_minutes=gap_threshold_minutes
    )
    ordered["track_id"] = ordered["source_vessel_id"].map(
        lambda value: surrogate_track_id(value, source_date)
    )
    public_columns = [
        "track_id",
        "base_date_time",
        "longitude",
        "latitude",
        *(field for field in ("sog", "cog", "heading", "vessel_type") if field in ordered),
    ]
    public = ordered[public_columns].copy()
    selected, selection_stats = select_complete_tracks(
        public, max_observations=max_observations
    )
    if filtered_rows > 0 and selected.empty:
        raise ValueError(
            "no complete tracks fit within the observation ceiling "
            f"{max_observations}; skipped={len(selection_stats.skipped_track_ids)}, "
            f"oversized={len(selection_stats.oversized_track_ids)}"
        )
    measurement_fields = [
        field for field in ("sog", "cog", "heading", "vessel_type") if field in selected
    ]
    missing_rates = {
        field: (float(selected[field].isna().mean()) if len(selected) else 0.0)
        for field in measurement_fields
    }
    return ProcessingResult(
        frame=selected,
        source_rows=int(source_rows),
        invalid_coordinate_rows=invalid_coordinate_rows,
        invalid_timestamp_rows=invalid_timestamp_rows,
        invalid_identifier_rows=invalid_identifier_rows,
        bbox_rows=int(bbox_rows),
        filtered_rows=int(filtered_rows),
        output_rows=int(len(selected)),
        vessel_count=int(selected["track_id"].nunique()),
        duplicate_stats=duplicate_stats,
        time_gap_stats=time_gap_stats,
        selection_stats=selection_stats,
        source_columns=source_columns,
        output_columns=tuple(str(name) for name in selected.columns),
        missing_rates=missing_rates,
    )


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as source:
        while chunk := source.read(1_048_576):
            digest.update(chunk)
    return digest.hexdigest()


def _assert_public_columns(frame: pd.DataFrame) -> None:
    forbidden = {"mmsi", "source_vessel_id", "source_id"}
    exposed = forbidden.intersection(name.lower() for name in frame.columns)
    if exposed:
        raise ValueError(f"public output contains forbidden identifiers: {sorted(exposed)}")


def write_processed_parquet(
    frame: pd.DataFrame, path: Path, *, overwrite: bool = False
) -> ArtifactRecord:
    _assert_public_columns(frame)
    path = Path(path)
    if path.exists() and not overwrite:
        raise FileExistsError(f"destination already exists: {path}")
    partial = path.with_name(path.name + ".partial")
    if partial.exists() and not overwrite:
        raise FileExistsError(f"partial output already exists: {partial}")
    if partial.exists():
        partial.unlink()
    path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pandas(frame, preserve_index=False)
    metadata = dict(table.schema.metadata or {})
    metadata.update(
        {
            b"seawatch_crs": b"EPSG:4326",
            b"seawatch_timezone": b"UTC",
        }
    )
    table = table.replace_schema_metadata(metadata)
    pq.write_table(table, partial)
    partial.replace(path)
    return ArtifactRecord(
        path=path,
        size_bytes=path.stat().st_size,
        row_count=len(frame),
        sha256=_file_sha256(path),
    )


def write_geojson_preview(
    frame: pd.DataFrame,
    path: Path,
    *,
    max_tracks: int,
    overwrite: bool = False,
) -> ArtifactRecord:
    _assert_public_columns(frame)
    if max_tracks <= 0:
        raise ValueError("max_tracks must be positive")
    required = {"track_id", "base_date_time", "longitude", "latitude"}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"missing GeoJSON columns: {', '.join(missing)}")
    path = Path(path)
    if path.exists() and not overwrite:
        raise FileExistsError(f"destination already exists: {path}")
    partial = path.with_name(path.name + ".partial")
    if partial.exists() and not overwrite:
        raise FileExistsError(f"partial output already exists: {partial}")
    if partial.exists():
        partial.unlink()

    selected_ids = sorted(frame["track_id"].astype(str).unique())[:max_tracks]
    features: list[dict[str, object]] = []
    included_rows = 0
    for track_id in selected_ids:
        track = frame.loc[frame["track_id"].astype(str).eq(track_id)].sort_values(
            "base_date_time", kind="mergesort"
        )
        coordinates = [
            [float(longitude), float(latitude)]
            for longitude, latitude in zip(
                track["longitude"], track["latitude"], strict=True
            )
        ]
        included_rows += len(track)
        geometry: dict[str, object]
        if len(coordinates) == 1:
            geometry = {"type": "Point", "coordinates": coordinates[0]}
        else:
            geometry = {"type": "LineString", "coordinates": coordinates}
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "track_id": track_id,
                    "observation_count": int(len(track)),
                    "start_utc": track["base_date_time"].iloc[0].isoformat().replace(
                        "+00:00", "Z"
                    ),
                    "end_utc": track["base_date_time"].iloc[-1].isoformat().replace(
                        "+00:00", "Z"
                    ),
                },
                "geometry": geometry,
            }
        )
    payload = {
        "type": "FeatureCollection",
        "name": "SeaWatch NOAA AIS smoke preview",
        "features": features,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    partial.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    partial.replace(path)
    return ArtifactRecord(
        path=path,
        size_bytes=path.stat().st_size,
        row_count=included_rows,
        sha256=_file_sha256(path),
    )


def build_manifest(
    result: ProcessingResult,
    *,
    dataset_id: str,
    publisher: str,
    source_url: str,
    source_readme_url: str,
    observed_license: str | None,
    license_url: str | None,
    download_utc: datetime,
    source_date: date,
    content_length: int,
    source_sha256: str,
    source_inspection: Mapping[str, object],
    bbox: BoundingBox,
    processing_version: str,
    git_reference: str | None,
    notes: list[str],
) -> dict[str, object]:
    if download_utc.tzinfo is None:
        raise ValueError("download_utc must be timezone-aware")
    manifest_notes = list(notes)
    manifest_notes.append(
        "track_id is a deterministic display surrogate; hashing does not prevent re-identification by enumeration."
    )
    return {
        "dataset_id": dataset_id,
        "publisher": publisher,
        "source_url": source_url,
        "source_readme_url": source_readme_url,
        "observed_license": observed_license,
        "license_url": license_url,
        "download_utc": download_utc.isoformat().replace("+00:00", "Z"),
        "source_date": source_date.isoformat(),
        "content_length": int(content_length),
        "sha256": source_sha256,
        "geographic_bbox": {
            "west": bbox.west,
            "south": bbox.south,
            "east": bbox.east,
            "north": bbox.north,
        },
        "vessel_type_filter": {
            "field": "vessel_type",
            "codes": list(range(70, 80)),
            "description": "AIS cargo vessel type codes 70 through 79",
        },
        "source_columns": source_inspection.get("columns"),
        "output_columns": list(result.output_columns),
        "crs": "EPSG:4326",
        "timezone": "UTC",
        "source_rows": source_inspection.get("row_count", result.source_rows),
        "bbox_rows": result.bbox_rows,
        "filtered_rows": result.filtered_rows,
        "output_rows": result.output_rows,
        "surrogate_id_method": (
            "first 16 lowercase hexadecimal characters of SHA-256 over "
            "seawatch:noaa-ais:<source-date>:<normalized-source-identifier>"
        ),
        "processing_version": processing_version,
        "git_commit_or_version_reference": git_reference,
        "synthetic_fields": ["track_id", "longitude", "latitude"],
        "notes": manifest_notes,
    }


def _format_rate(value: float | None) -> str:
    return "not measured" if value is None else f"{value:.4%}"


def render_qa_report(
    result: ProcessingResult,
    *,
    source_file_size: int,
    source_metadata_rows: int | None,
    processed_artifact: ArtifactRecord,
    geojson_artifact: ArtifactRecord,
    bbox: BoundingBox,
) -> str:
    if len(result.frame):
        timestamp_min = result.frame["base_date_time"].min().isoformat().replace(
            "+00:00", "Z"
        )
        timestamp_max = result.frame["base_date_time"].max().isoformat().replace(
            "+00:00", "Z"
        )
    else:
        timestamp_min = timestamp_max = "not measured"
    gap = result.time_gap_stats
    threshold_minutes = gap.threshold_seconds / 60
    coordinate_valid_rows = result.source_rows - result.invalid_coordinate_rows
    coordinate_validity_rate = (
        coordinate_valid_rows / result.source_rows if result.source_rows else None
    )
    rows = [
        ("Source file size (bytes)", str(source_file_size)),
        ("Source metadata row count", str(source_metadata_rows) if source_metadata_rows is not None else "not measured"),
        ("Selected bbox", f"[{bbox.west}, {bbox.south}, {bbox.east}, {bbox.north}]"),
        ("BBox rows", str(result.bbox_rows)),
        ("Cargo-filter rows (before exact deduplication)", str(result.filtered_rows)),
        ("Number of vessels/tracks", str(result.vessel_count)),
        ("Timestamp range (UTC)", f"{timestamp_min} to {timestamp_max}"),
        ("SOG missing rate", _format_rate(result.missing_rates.get("sog"))),
        ("COG missing rate", _format_rate(result.missing_rates.get("cog"))),
        ("Heading missing rate", _format_rate(result.missing_rates.get("heading"))),
        ("Vessel type missing rate", _format_rate(result.missing_rates.get("vessel_type"))),
        ("Coordinate-valid source rows", str(coordinate_valid_rows)),
        ("Coordinate validity rate", _format_rate(coordinate_validity_rate)),
        ("Invalid coordinate rows", str(result.invalid_coordinate_rows)),
        ("Invalid timestamp rows", str(result.invalid_timestamp_rows)),
        ("Invalid source-identifier rows", str(result.invalid_identifier_rows)),
        ("Eligible cargo exact duplicate observations removed", str(result.duplicate_stats.exact_duplicate_rows)),
        ("Eligible cargo duplicate-timestamp rows retained", str(result.duplicate_stats.duplicate_timestamp_rows)),
        ("Eligible cargo time-gap observation pairs", str(gap.observation_pairs)),
        ("Eligible cargo positive time gaps", str(gap.positive_gap_count)),
        ("Eligible cargo zero time gaps", str(gap.zero_gap_count)),
        ("Eligible cargo negative time gaps", str(gap.negative_gap_count)),
        (f"Eligible cargo gaps greater than {threshold_minutes:g} minutes", str(gap.gaps_over_threshold_count)),
        ("Eligible cargo minimum positive gap (seconds)", str(gap.minimum_positive_seconds) if gap.minimum_positive_seconds is not None else "not measured"),
        ("Eligible cargo median positive gap (seconds)", str(gap.median_positive_seconds) if gap.median_positive_seconds is not None else "not measured"),
        ("Eligible cargo maximum positive gap (seconds)", str(gap.maximum_positive_seconds) if gap.maximum_positive_seconds is not None else "not measured"),
        ("Tracks skipped by the observation ceiling", str(len(result.selection_stats.skipped_track_ids))),
        ("Oversized tracks skipped", str(len(result.selection_stats.oversized_track_ids))),
        ("Final processed rows", str(result.output_rows)),
        ("Processed Parquet size (bytes)", str(processed_artifact.size_bytes)),
        ("GeoJSON preview size (bytes)", str(geojson_artifact.size_bytes)),
    ]
    table = "\n".join(f"| {name} | {value} |" for name, value in rows)
    return (
        "# NOAA AIS Data Foundation QA Report\n\n"
        "Measured from the official source and generated Phase 1 artifacts. "
        "Metrics prefixed `Eligible cargo` describe valid in-bbox cargo observations "
        "before the complete-track ceiling; vessel, timestamp, missing-rate, and final-row "
        "metrics describe the selected output.\n\n"
        "| Metric | Observed value |\n|---|---:|\n"
        f"{table}\n"
    )


def canonicalize_observations(
    frame: pd.DataFrame,
    column_map: Mapping[str, str],
    *,
    source_crs: object | None,
) -> pd.DataFrame:
    required = ("source_vessel_id", "base_date_time")
    missing_semantics = [name for name in required if name not in column_map]
    if missing_semantics:
        raise ValueError(f"missing required field mapping: {', '.join(missing_semantics)}")
    missing_columns = [
        source_name for source_name in column_map.values() if source_name not in frame
    ]
    if missing_columns:
        raise ValueError(f"source columns not found: {', '.join(missing_columns)}")
    has_geometry = "geometry" in column_map
    has_coordinates = "longitude" in column_map and "latitude" in column_map
    if not has_geometry and not has_coordinates:
        raise ValueError("a geometry or longitude/latitude mapping is required")
    if source_crs is None:
        raise ValueError("source CRS is required before coordinates can be interpreted")
    try:
        source_reference = CRS.from_user_input(source_crs)
    except CRSError as error:
        raise ValueError(f"unsupported source CRS: {source_crs!r}") from error

    result = pd.DataFrame(index=frame.index)
    result["source_vessel_id"] = (
        frame[column_map["source_vessel_id"]].astype("string").str.strip()
    )
    result["base_date_time"] = parse_utc_timestamps(
        frame[column_map["base_date_time"]]
    )

    if has_geometry:
        geometries = from_wkb(frame[column_map["geometry"]].to_numpy())
        unsupported = ~(is_missing(geometries) | is_empty(geometries)) & (
            get_type_id(geometries) != 0
        )
        if unsupported.any():
            observed = sorted(
                {str(geometry.geom_type) for geometry in geometries[unsupported]}
            )
            raise ValueError(
                f"only Point geometry is supported, observed {', '.join(observed)}"
            )
        longitude = pd.Series(get_x(geometries), index=frame.index)
        latitude = pd.Series(get_y(geometries), index=frame.index)
    else:
        longitude = pd.to_numeric(frame[column_map["longitude"]], errors="coerce")
        latitude = pd.to_numeric(frame[column_map["latitude"]], errors="coerce")

    target_reference = CRS.from_epsg(4326)
    if not source_reference.equals(target_reference, ignore_axis_order=True):
        transformer = Transformer.from_crs(
            source_reference, target_reference, always_xy=True
        )
        transformed_lon, transformed_lat = transformer.transform(
            longitude.to_numpy(), latitude.to_numpy()
        )
        longitude = pd.Series(transformed_lon, index=frame.index)
        latitude = pd.Series(transformed_lat, index=frame.index)

    result["longitude"] = longitude
    result["latitude"] = latitude
    for field in ("sog", "cog", "heading", "vessel_type"):
        if field in column_map:
            result[field] = frame[column_map[field]]
    return result
