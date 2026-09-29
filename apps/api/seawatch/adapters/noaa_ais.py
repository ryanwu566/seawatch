"""Acquisition helpers for official NOAA/MarineCadastre AIS data."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from http.client import IncompleteRead
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

import json

import pyarrow as pa
import pyarrow.parquet as pq


@dataclass(frozen=True)
class DownloadRecord:
    source_url: str
    destination: Path
    content_length: int
    sha256: str
    download_utc: datetime


class DownloadError(RuntimeError):
    """Raised when an official-source transfer cannot complete safely."""


class MetadataInspectionError(RuntimeError):
    """Raised when Parquet metadata cannot be interpreted safely."""


@dataclass(frozen=True)
class ColumnInspection:
    name: str
    type: str
    nullable: bool

    def to_dict(self) -> dict[str, object]:
        return {"name": self.name, "type": self.type, "nullable": self.nullable}


@dataclass(frozen=True)
class ParquetInspection:
    path: Path
    row_count: int
    row_group_count: int
    columns: tuple[ColumnInspection, ...]
    timestamp_columns: dict[str, str]
    parquet_metadata: dict[str, str]
    geoparquet: dict[str, object] | None
    geometry_column: str | None
    geometry_encoding: str | None
    geometry_types: tuple[str, ...]
    crs: object | None

    def to_dict(self) -> dict[str, object]:
        return {
            "path": str(self.path),
            "row_count": self.row_count,
            "row_group_count": self.row_group_count,
            "columns": [column.to_dict() for column in self.columns],
            "timestamp_columns": dict(self.timestamp_columns),
            "parquet_metadata": dict(self.parquet_metadata),
            "geoparquet": self.geoparquet,
            "geometry_column": self.geometry_column,
            "geometry_encoding": self.geometry_encoding,
            "geometry_types": list(self.geometry_types),
            "crs": self.crs,
        }


def write_download_record(
    record: DownloadRecord, path: Path, *, overwrite: bool = False
) -> None:
    path = Path(path)
    if path.exists() and not overwrite:
        raise FileExistsError(f"download record already exists: {path}")
    if record.download_utc.tzinfo is None:
        raise ValueError("download_utc must be timezone-aware")
    payload = {
        "source_url": record.source_url,
        "destination": str(record.destination),
        "content_length": record.content_length,
        "sha256": record.sha256,
        "download_utc": record.download_utc.isoformat().replace("+00:00", "Z"),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name + ".partial")
    partial.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    partial.replace(path)


def read_download_record(path: Path) -> DownloadRecord:
    path = Path(path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        timestamp = datetime.fromisoformat(
            str(payload["download_utc"]).replace("Z", "+00:00")
        )
        if timestamp.tzinfo is None:
            raise ValueError("download_utc must be timezone-aware")
        return DownloadRecord(
            source_url=str(payload["source_url"]),
            destination=Path(str(payload["destination"])),
            content_length=int(payload["content_length"]),
            sha256=str(payload["sha256"]),
            download_utc=timestamp,
        )
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise DownloadError(f"invalid download record {path}: {error}") from error


def inspect_parquet(path: Path) -> ParquetInspection:
    path = Path(path)
    try:
        parquet = pq.ParquetFile(path)
    except (OSError, pa.ArrowInvalid) as error:
        raise MetadataInspectionError(
            f"cannot inspect Parquet file {path}: {error}"
        ) from error
    schema = parquet.schema_arrow
    metadata = {
        key.decode("utf-8", errors="replace"): value.decode(
            "utf-8", errors="replace"
        )
        for key, value in (schema.metadata or {}).items()
    }
    try:
        geoparquet = json.loads(metadata["geo"]) if "geo" in metadata else None
    except json.JSONDecodeError as error:
        raise MetadataInspectionError(
            f"invalid GeoParquet JSON in {path}: {error}"
        ) from error
    if geoparquet is not None:
        if not isinstance(geoparquet, dict):
            raise MetadataInspectionError(
                f"invalid GeoParquet metadata in {path}: expected an object"
            )
        primary = geoparquet.get("primary_column")
        columns_metadata = geoparquet.get("columns")
        if not isinstance(primary, str) or not isinstance(columns_metadata, dict):
            raise MetadataInspectionError(
                f"invalid GeoParquet metadata in {path}: primary_column and columns are required"
            )
        if primary not in columns_metadata:
            raise MetadataInspectionError(
                f"invalid GeoParquet metadata in {path}: primary_column {primary!r} is absent from columns"
            )
    geometry_column = geoparquet.get("primary_column") if geoparquet else None
    geometry_details = (
        geoparquet.get("columns", {}).get(geometry_column, {})
        if geoparquet and geometry_column
        else {}
    )
    columns = tuple(
        ColumnInspection(field.name, str(field.type), field.nullable)
        for field in schema
    )
    timestamps = {
        field.name: str(field.type) for field in schema if pa.types.is_timestamp(field.type)
    }
    return ParquetInspection(
        path=path,
        row_count=parquet.metadata.num_rows,
        row_group_count=parquet.metadata.num_row_groups,
        columns=columns,
        timestamp_columns=timestamps,
        parquet_metadata=metadata,
        geoparquet=geoparquet,
        geometry_column=geometry_column,
        geometry_encoding=geometry_details.get("encoding"),
        geometry_types=tuple(geometry_details.get("geometry_types", [])),
        crs=geometry_details.get("crs"),
    )


def sha256_file(path: Path, chunk_size: int = 1_048_576) -> str:
    digest = sha256()
    with path.open("rb") as source:
        while chunk := source.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def download_file(
    source_url: str,
    destination: Path,
    *,
    overwrite: bool = False,
    chunk_size: int = 1_048_576,
) -> DownloadRecord:
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(destination.name + ".partial")
    if destination.exists() and not overwrite:
        raise FileExistsError(f"destination already exists: {destination}")
    if partial.exists():
        if not overwrite:
            raise FileExistsError(f"partial download already exists: {partial}")
        partial.unlink()

    digest = sha256()
    content_length = 0

    try:
        with urlopen(source_url) as response, partial.open("wb") as output:
            expected_length_header = response.headers.get("Content-Length")
            expected_length = (
                int(expected_length_header) if expected_length_header is not None else None
            )
            while chunk := response.read(chunk_size):
                output.write(chunk)
                digest.update(chunk)
                content_length += len(chunk)
        if expected_length is not None and content_length != expected_length:
            raise DownloadError(
                f"incomplete download from {source_url}: expected {expected_length} bytes, "
                f"received {content_length}"
            )
    except HTTPError as error:
        raise DownloadError(
            f"HTTP {error.code} while downloading {source_url}"
        ) from error
    except (IncompleteRead, URLError, OSError) as error:
        raise DownloadError(f"download failed for {source_url}: {error}") from error

    partial.replace(destination)
    return DownloadRecord(
        source_url=source_url,
        destination=destination,
        content_length=content_length,
        sha256=digest.hexdigest(),
        download_utc=datetime.now(timezone.utc),
    )
