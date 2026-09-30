from __future__ import annotations

from datetime import date, datetime, timezone
import json
from pathlib import Path
import sys

import pytest

from apps.api.seawatch.adapters.noaa_ais import DownloadRecord, ParquetInspection
from scripts.prepare_smoke_dataset import (
    APPROVED_SOURCE_URL,
    default_daily_paths,
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


@pytest.mark.parametrize("source_date", [date(2024, 1, 2), date(2024, 1, 3)])
def test_preparation_defaults_are_isolated_by_source_date(source_date: date) -> None:
    rendered = source_date.isoformat()

    paths = default_daily_paths(source_date)

    assert paths == {
        "source": Path(f"data/raw/ais-{rendered}.parquet"),
        "processed": Path(f"data/processed/noaa_ais_{rendered}_sf_bay.parquet"),
        "preview": Path(
            f"data/processed/noaa_ais_{rendered}_sf_bay_preview.geojson"
        ),
        "manifest": Path(f"data/manifests/noaa_ais_{rendered}_sf_bay.json"),
        "report": Path(f"docs/qa/noaa-ais-{rendered}-data-foundation.md"),
    }


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


@pytest.mark.parametrize("source_date", ["2024-01-02", "2024-01-03"])
def test_download_cli_resolves_approved_date_before_mocked_transfer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, source_date: str
) -> None:
    destination = tmp_path / f"ais-{source_date}.parquet"
    calls: list[tuple[str, Path, bool]] = []

    def fake_download(source_url: str, output: Path, *, overwrite: bool = False):
        calls.append((source_url, output, overwrite))
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"synthetic NOAA bytes")
        return DownloadRecord(
            source_url=source_url,
            destination=output,
            content_length=20,
            sha256="a" * 64,
            download_utc=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )

    monkeypatch.setattr(download_noaa_ais, "download_file", fake_download)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "download_noaa_ais.py",
            "--date", source_date,
            "--destination", str(destination),
        ],
    )

    assert download_noaa_ais.main() == 0
    expected_url = (
        "https://ocmgeodatastor1.blob.core.windows.net/"
        f"marinecadastre/ais2024/ais-{source_date}.parquet"
    )
    assert calls == [(expected_url, destination, False)]
    record = json.loads(
        destination.with_name(destination.name + ".download.json").read_text(
            encoding="utf-8"
        )
    )
    assert record["source_url"] == expected_url


def test_download_cli_rejects_unapproved_date_before_transport_or_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    destination = tmp_path / "ais-2024-01-04.parquet"

    def forbidden_transport(*args, **kwargs):
        raise AssertionError("transport must not be called")

    monkeypatch.setattr(download_noaa_ais, "download_file", forbidden_transport)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "download_noaa_ais.py",
            "--date", "2024-01-04",
            "--destination", str(destination),
        ],
    )

    with pytest.raises(SystemExit) as error:
        download_noaa_ais.main()

    assert error.value.code == 1
    assert not destination.exists()
