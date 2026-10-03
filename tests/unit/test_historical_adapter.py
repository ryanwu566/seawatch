from __future__ import annotations

from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest


def _write_daily(path: Path, rows: list[dict[str, object]]) -> None:
    pq.write_table(pa.Table.from_pylist(rows), path)


def _row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "date": "2026-09-01 08:00",
        "lat": 25.8,
        "lon": 119.59,
        "vesselId": "gfw-vessel-1",
        "mmsi": "416000001",
    }
    row.update(overrides)
    return row


def test_gfw_adapter_normalizes_timestamp_and_keeps_mmsi_internal(
    tmp_path: Path,
) -> None:
    from apps.api.seawatch.historical.adapter import GfwPresenceParquetAdapter

    _write_daily(tmp_path / "gfw_taiwan_2026-09-01.parquet", [_row()])

    record = list(GfwPresenceParquetAdapter(tmp_path).load_tracks())[0]

    assert record.observed_at == "2026-09-01T08:00:00Z"
    assert record.data_source == "gfw_presence"
    assert record.mmsi == 416000001
    assert record.sog_knots is None
    assert record.cog_deg is None
    assert record.heading_deg is None
    assert record.vessel_type is None
    assert "416000001" not in repr(record)


def test_gfw_adapter_accepts_files_without_optional_mmsi(tmp_path: Path) -> None:
    from apps.api.seawatch.historical.adapter import GfwPresenceParquetAdapter

    row = _row()
    del row["mmsi"]
    _write_daily(tmp_path / "gfw_taiwan_2026-09-01.parquet", [row])

    record = list(GfwPresenceParquetAdapter(tmp_path).load_tracks())[0]

    assert record.mmsi is None


def test_gfw_adapter_reads_daily_files_in_deterministic_filename_order(
    tmp_path: Path,
) -> None:
    from apps.api.seawatch.historical.adapter import GfwPresenceParquetAdapter

    _write_daily(
        tmp_path / "gfw_taiwan_2026-09-02.parquet",
        [_row(date="2026-09-02 08:00", vesselId="second")],
    )
    _write_daily(
        tmp_path / "gfw_taiwan_2026-09-01.parquet",
        [_row(date="2026-09-01 08:00", vesselId="first")],
    )

    records = list(GfwPresenceParquetAdapter(tmp_path).load_tracks())

    assert [record.vessel_id for record in records] == ["first", "second"]


def test_gfw_adapter_reports_missing_required_parquet_columns(tmp_path: Path) -> None:
    from apps.api.seawatch.historical.adapter import GfwPresenceParquetAdapter

    row = _row()
    del row["lon"]
    _write_daily(tmp_path / "gfw_taiwan_2026-09-01.parquet", [row])

    with pytest.raises(ValueError, match=r"missing required columns \(lon\)"):
        list(GfwPresenceParquetAdapter(tmp_path).load_tracks())


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"lat": 90.1}, "latitude"),
        ({"lon": -180.1}, "longitude"),
    ],
)
def test_gfw_adapter_rejects_invalid_coordinates(
    tmp_path: Path,
    overrides: dict[str, object],
    message: str,
) -> None:
    from apps.api.seawatch.historical.adapter import GfwPresenceParquetAdapter

    _write_daily(
        tmp_path / "gfw_taiwan_2026-09-01.parquet",
        [_row(**overrides)],
    )

    with pytest.raises(ValueError, match=message):
        list(GfwPresenceParquetAdapter(tmp_path).load_tracks())


@pytest.mark.parametrize("mmsi", [None, "", "not-an-mmsi", 123, 416000001.5])
def test_gfw_adapter_treats_unusable_mmsi_as_unjoinable(
    tmp_path: Path,
    mmsi: object,
) -> None:
    from apps.api.seawatch.historical.adapter import GfwPresenceParquetAdapter

    _write_daily(
        tmp_path / "gfw_taiwan_2026-09-01.parquet",
        [_row(mmsi=mmsi)],
    )

    record = list(GfwPresenceParquetAdapter(tmp_path).load_tracks())[0]

    assert record.mmsi is None
