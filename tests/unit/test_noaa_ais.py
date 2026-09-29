from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
import json

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from shapely.geometry import Point

from apps.api.seawatch.adapters.noaa_ais import (
    DownloadError,
    MetadataInspectionError,
    download_file,
    inspect_parquet,
    read_download_record,
    sha256_file,
    write_download_record,
)


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        pass


@contextmanager
def _serve(directory: Path):
    handler = partial(_QuietHandler, directory=str(directory))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


@contextmanager
def _serve_handler(handler_type: type[SimpleHTTPRequestHandler]):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_type)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


class _TruncatedHandler(SimpleHTTPRequestHandler):
    def do_GET(self) -> None:
        self.send_response(200)
        self.send_header("Content-Length", "100")
        self.end_headers()
        self.wfile.write(b"short")
        self.wfile.flush()
        self.close_connection = True

    def log_message(self, format: str, *args: object) -> None:
        pass


def test_sha256_file_returns_digest_for_file_bytes(tmp_path: Path) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"hello ais\n")

    assert (
        sha256_file(source)
        == "387cfa704b6cbe82d55f9903c22fb85efbc7c47218970354bfb16722d15af226"
    )


def test_successful_download_streams_exact_bytes_and_records_provenance(
    tmp_path: Path,
) -> None:
    source_dir = tmp_path / "server"
    source_dir.mkdir()
    payload = b"hello ais\n"
    (source_dir / "daily.parquet").write_bytes(payload)
    destination = tmp_path / "raw" / "daily.parquet"

    with _serve(source_dir) as base_url:
        source_url = f"{base_url}/daily.parquet"
        record = download_file(source_url, destination, chunk_size=3)

    assert destination.read_bytes() == payload
    assert record.source_url == source_url
    assert record.destination == destination
    assert record.content_length == len(payload)
    assert (
        record.sha256
        == "387cfa704b6cbe82d55f9903c22fb85efbc7c47218970354bfb16722d15af226"
    )
    assert record.download_utc.tzinfo is timezone.utc
    assert not destination.with_name(destination.name + ".partial").exists()


def test_existing_destination_is_not_overwritten_without_permission(
    tmp_path: Path,
) -> None:
    source_dir = tmp_path / "server"
    source_dir.mkdir()
    (source_dir / "daily.parquet").write_bytes(b"replacement")
    destination = tmp_path / "daily.parquet"
    destination.write_bytes(b"keep me")

    with _serve(source_dir) as base_url:
        with pytest.raises(FileExistsError, match="already exists"):
            download_file(f"{base_url}/daily.parquet", destination)

    assert destination.read_bytes() == b"keep me"


def test_overwrite_replaces_existing_destination_when_explicit(tmp_path: Path) -> None:
    source_dir = tmp_path / "server"
    source_dir.mkdir()
    (source_dir / "daily.parquet").write_bytes(b"replacement")
    destination = tmp_path / "daily.parquet"
    destination.write_bytes(b"old")

    with _serve(source_dir) as base_url:
        download_file(f"{base_url}/daily.parquet", destination, overwrite=True)

    assert destination.read_bytes() == b"replacement"


def test_http_failure_names_status_and_source_url(tmp_path: Path) -> None:
    source_dir = tmp_path / "server"
    source_dir.mkdir()
    destination = tmp_path / "daily.parquet"

    with _serve(source_dir) as base_url:
        source_url = f"{base_url}/missing.parquet"
        with pytest.raises(DownloadError) as error:
            download_file(source_url, destination)

    message = str(error.value)
    assert "404" in message
    assert source_url in message
    assert not destination.exists()


def test_partial_transfer_never_creates_final_destination(tmp_path: Path) -> None:
    destination = tmp_path / "daily.parquet"

    with _serve_handler(_TruncatedHandler) as base_url:
        with pytest.raises(DownloadError, match="incomplete"):
            download_file(f"{base_url}/daily.parquet", destination)

    assert not destination.exists()
    assert destination.with_name(destination.name + ".partial").exists()


def test_stale_partial_is_not_silently_treated_as_success(tmp_path: Path) -> None:
    source_dir = tmp_path / "server"
    source_dir.mkdir()
    (source_dir / "daily.parquet").write_bytes(b"new")
    destination = tmp_path / "daily.parquet"
    partial = destination.with_name(destination.name + ".partial")
    partial.write_bytes(b"stale")

    with _serve(source_dir) as base_url:
        with pytest.raises(FileExistsError, match="partial"):
            download_file(f"{base_url}/daily.parquet", destination)

    assert partial.read_bytes() == b"stale"
    assert not destination.exists()


def test_inspect_parquet_reports_actual_schema_and_geoparquet_metadata(
    tmp_path: Path,
) -> None:
    geo = {
        "version": "1.1.0",
        "primary_column": "geometry",
        "columns": {
            "geometry": {
                "encoding": "WKB",
                "geometry_types": ["Point"],
                "crs": {"id": {"authority": "EPSG", "code": 4326}},
            }
        },
    }
    schema = pa.schema(
        [
            pa.field("mmsi", pa.int64(), nullable=False),
            pa.field("base_date_time", pa.timestamp("ms", tz="UTC")),
            pa.field("geometry", pa.binary()),
        ],
        metadata={b"geo": json.dumps(geo).encode("utf-8"), b"publisher": b"test"},
    )
    table = pa.Table.from_arrays(
        [
            pa.array([111, 222], type=pa.int64()),
            pa.array(
                [
                    datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc),
                    datetime(2024, 1, 1, 0, 1, tzinfo=timezone.utc),
                ],
                type=pa.timestamp("ms", tz="UTC"),
            ),
            pa.array([Point(-122.4, 37.8).wkb, Point(-122.3, 37.9).wkb]),
        ],
        schema=schema,
    )
    path = tmp_path / "geo.parquet"
    pq.write_table(table, path, row_group_size=1)

    result = inspect_parquet(path).to_dict()

    assert result["row_count"] == 2
    assert result["row_group_count"] == 2
    assert result["columns"] == [
        {"name": "mmsi", "type": "int64", "nullable": False},
        {
            "name": "base_date_time",
            "type": "timestamp[ms, tz=UTC]",
            "nullable": True,
        },
        {"name": "geometry", "type": "binary", "nullable": True},
    ]
    assert result["timestamp_columns"] == {
        "base_date_time": "timestamp[ms, tz=UTC]"
    }
    assert result["parquet_metadata"]["publisher"] == "test"
    assert result["geoparquet"]["version"] == "1.1.0"
    assert result["geometry_column"] == "geometry"
    assert result["geometry_encoding"] == "WKB"
    assert result["geometry_types"] == ["Point"]
    assert result["crs"] == {"id": {"authority": "EPSG", "code": 4326}}


def test_inspect_parquet_reports_non_geoparquet_without_inventing_geometry(
    tmp_path: Path,
) -> None:
    path = tmp_path / "plain.parquet"
    pq.write_table(pa.table({"value": [1, 2]}), path)

    result = inspect_parquet(path).to_dict()

    assert result["row_count"] == 2
    assert result["geoparquet"] is None
    assert result["geometry_column"] is None
    assert result["geometry_encoding"] is None
    assert result["geometry_types"] == []
    assert result["crs"] is None


def test_inspect_parquet_rejects_malformed_geoparquet_json(tmp_path: Path) -> None:
    schema = pa.schema(
        [pa.field("geometry", pa.binary())], metadata={b"geo": b"not-json"}
    )
    path = tmp_path / "malformed.parquet"
    pq.write_table(pa.Table.from_arrays([pa.array([b"x"])], schema=schema), path)

    with pytest.raises(MetadataInspectionError, match="invalid GeoParquet JSON"):
        inspect_parquet(path)


def test_inspect_parquet_rejects_missing_primary_geometry(tmp_path: Path) -> None:
    geo = {"version": "1.1.0", "columns": {"geometry": {"encoding": "WKB"}}}
    schema = pa.schema(
        [pa.field("geometry", pa.binary())],
        metadata={b"geo": json.dumps(geo).encode("utf-8")},
    )
    path = tmp_path / "ambiguous.parquet"
    pq.write_table(pa.Table.from_arrays([pa.array([b"x"])], schema=schema), path)

    with pytest.raises(MetadataInspectionError, match="primary_column"):
        inspect_parquet(path)


def test_inspect_parquet_wraps_unreadable_or_invalid_file(tmp_path: Path) -> None:
    path = tmp_path / "not-parquet.txt"
    path.write_text("not parquet", encoding="utf-8")

    with pytest.raises(MetadataInspectionError, match="cannot inspect Parquet"):
        inspect_parquet(path)


def test_download_record_sidecar_round_trips_verified_values(tmp_path: Path) -> None:
    from apps.api.seawatch.adapters.noaa_ais import DownloadRecord

    record = DownloadRecord(
        source_url="https://example.invalid/daily.parquet",
        destination=tmp_path / "daily.parquet",
        content_length=123,
        sha256="a" * 64,
        download_utc=datetime(2024, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
    )
    sidecar = tmp_path / "daily.parquet.download.json"

    write_download_record(record, sidecar)
    restored = read_download_record(sidecar)

    assert restored == record
    assert json.loads(sidecar.read_text(encoding="utf-8"))["sha256"] == "a" * 64
