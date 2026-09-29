from __future__ import annotations

from pathlib import Path
import sys

import pytest

from apps.api.seawatch.adapters.noaa_ais import ParquetInspection
from scripts.prepare_smoke_dataset import (
    APPROVED_SOURCE_URL,
    main,
    resolve_mapped_location_crs,
)
from scripts import download_noaa_ais


def _inspection(*, primary: str = "geometry") -> ParquetInspection:
    return ParquetInspection(
        path=Path("fixture.parquet"),
        row_count=1,
        row_group_count=1,
        columns=(),
        timestamp_columns={},
        parquet_metadata={},
        geoparquet={
            "version": "1.0.0",
            "primary_column": primary,
            "columns": {
                "geometry": {
                    "encoding": "WKB",
                    "geometry_types": ["Point"],
                    "crs": {"id": {"authority": "EPSG", "code": 4326}},
                },
                "secondary": {
                    "encoding": "WKB",
                    "geometry_types": ["Point"],
                    "crs": {"id": {"authority": "EPSG", "code": 3857}},
                },
            },
        },
        geometry_column=primary,
        geometry_encoding="WKB",
        geometry_types=("Point",),
        crs={"id": {"authority": "EPSG", "code": 4326}},
    )


def test_cli_preflights_all_outputs_before_reading_or_writing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text("committed measured manifest\n", encoding="utf-8")
    processed = tmp_path / "processed.parquet"
    preview = tmp_path / "preview.geojson"
    report = tmp_path / "report.md"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "prepare_smoke_dataset.py",
            "--source", str(tmp_path / "missing.parquet"),
            "--processed-output", str(processed),
            "--preview-output", str(preview),
            "--manifest-output", str(manifest),
            "--report-output", str(report),
            "--publisher", "NOAA Office for Coastal Management",
            "--observed-license", "CC0 1.0 Universal",
            "--license-url", "https://example.invalid/license",
        ],
    )

    with pytest.raises(SystemExit) as error:
        main()

    assert error.value.code == 1
    assert manifest.read_text(encoding="utf-8") == "committed measured manifest\n"
    assert not processed.exists()
    assert not preview.exists()
    assert not report.exists()


def test_mapped_geometry_uses_its_own_crs_not_the_primary_crs() -> None:
    assert resolve_mapped_location_crs(
        _inspection(), {"geometry": "secondary"}
    ) == {"id": {"authority": "EPSG", "code": 3857}}


def test_mapped_geometry_rejects_unsupported_encoding() -> None:
    inspection = _inspection()
    assert inspection.geoparquet is not None
    inspection.geoparquet["columns"]["secondary"]["encoding"] = "point"

    with pytest.raises(ValueError, match="WKB"):
        resolve_mapped_location_crs(inspection, {"geometry": "secondary"})


def test_production_preparation_rejects_unverified_coordinate_mapping() -> None:
    with pytest.raises(ValueError, match="coordinate-column mappings"):
        resolve_mapped_location_crs(
            _inspection(), {"longitude": "lon", "latitude": "lat"}
        )


def test_preparation_rejects_sidecar_from_unapproved_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "missing.parquet"
    sidecar = source.with_name(source.name + ".download.json")
    sidecar.write_text(
        '{"source_url":"https://example.invalid/other.parquet",'
        '"destination":"missing.parquet","content_length":0,'
        '"sha256":"' + "a" * 64 + '",'
        '"download_utc":"2024-01-01T00:00:00Z"}',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "prepare_smoke_dataset.py",
            "--source", str(source),
            "--download-record", str(sidecar),
            "--processed-output", str(tmp_path / "processed.parquet"),
            "--preview-output", str(tmp_path / "preview.geojson"),
            "--manifest-output", str(tmp_path / "manifest.json"),
            "--report-output", str(tmp_path / "report.md"),
            "--publisher", "NOAA Office for Coastal Management",
            "--observed-license", "CC0 1.0 Universal",
            "--license-url", "https://example.invalid/license",
        ],
    )

    with pytest.raises(SystemExit) as error:
        main()

    assert error.value.code == 1
    assert APPROVED_SOURCE_URL not in sidecar.read_text(encoding="utf-8")


def test_download_cli_rejects_unapproved_url_before_network_or_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    destination = tmp_path / "raw.parquet"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "download_noaa_ais.py",
            "--url", "https://example.invalid/other.parquet",
            "--destination", str(destination),
        ],
    )

    with pytest.raises(SystemExit) as error:
        download_noaa_ais.main()

    assert error.value.code == 1
    assert not destination.exists()
