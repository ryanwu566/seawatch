from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from io import StringIO
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq


def _write_smoke_fixture(root: Path) -> None:
    directory = root / "ais" / "historical" / "processed" / "daily"
    directory.mkdir(parents=True)
    start = datetime(2026, 9, 1, tzinfo=timezone.utc)
    for day in range(5):
        rows = []
        for hour in range(3):
            observed_at = start + timedelta(days=day, hours=hour)
            rows.append(
                {
                    "date": observed_at.strftime("%Y-%m-%d %H:%M"),
                    "lat": 22.0 + 0.0002 * (day % 2),
                    "lon": 120.0 + 0.1 * hour,
                    "vesselId": "raw-gfw-vessel-id",
                    "mmsi": "416000001",
                }
            )
        rows.append(
            {
                "date": (start + timedelta(days=day, hours=8)).strftime(
                    "%Y-%m-%d %H:%M"
                ),
                "lat": 23.0,
                "lon": 121.0,
                "vesselId": f"unjoinable-{day}",
                "mmsi": None,
            }
        )
        pq.write_table(
            pa.Table.from_pylist(rows),
            directory / f"gfw_taiwan_2026-09-{day + 1:02d}.parquet",
        )


def _clock() -> Callable[[], float]:
    values = iter((10.0, 12.5))
    return lambda: next(values)


def test_smoke_script_prints_aggregate_diagnostics_only(tmp_path: Path) -> None:
    from scripts.smoke_gfw_historical import main

    _write_smoke_fixture(tmp_path)
    stdout = StringIO()
    stderr = StringIO()

    exit_code = main(
        environ={
            "SEAWATCH_DATA_ROOT": str(tmp_path),
            "SEAWATCH_IDENTITY_KEY": "shared-live-history-key",
        },
        stdout=stdout,
        stderr=stderr,
        clock=_clock(),
    )

    assert exit_code == 0
    assert stderr.getvalue() == ""
    assert stdout.getvalue().splitlines() == [
        "discovered_parquet_file_count: 5",
        "observations_considered: 20",
        "observations_joinable_by_valid_mmsi: 15",
        "observations_excluded_from_live_identity_join: 5",
        "grouped_vessel_count: 1",
        "vessel_baseline_count: 1",
        "sufficient_baseline_count: 1",
        "insufficient_baseline_count: 0",
        "elapsed_runtime_seconds: 2.500",
    ]
    output = stdout.getvalue()
    assert "416000001" not in output
    assert "raw-gfw-vessel-id" not in output
    assert "v_" not in output


def test_smoke_script_fails_clearly_when_data_root_is_unavailable() -> None:
    from scripts.smoke_gfw_historical import main

    stdout = StringIO()
    stderr = StringIO()

    exit_code = main(
        environ={"SEAWATCH_IDENTITY_KEY": "secret-not-for-output"},
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code != 0
    assert stdout.getvalue() == ""
    assert "SEAWATCH_DATA_ROOT" in stderr.getvalue()
    assert "secret-not-for-output" not in stderr.getvalue()


def test_smoke_script_fails_clearly_when_identity_configuration_is_unavailable(
    tmp_path: Path,
) -> None:
    from scripts.smoke_gfw_historical import main

    stdout = StringIO()
    stderr = StringIO()

    exit_code = main(
        environ={"SEAWATCH_DATA_ROOT": str(tmp_path)},
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code != 0
    assert stdout.getvalue() == ""
    assert "SEAWATCH_IDENTITY_KEY" in stderr.getvalue()


def test_smoke_script_fails_clearly_when_parquet_data_is_unavailable(
    tmp_path: Path,
) -> None:
    from scripts.smoke_gfw_historical import main

    stdout = StringIO()
    stderr = StringIO()

    exit_code = main(
        environ={
            "SEAWATCH_DATA_ROOT": str(tmp_path),
            "SEAWATCH_IDENTITY_KEY": "secret-not-for-output",
        },
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code != 0
    assert stdout.getvalue() == ""
    assert "GFW parquet directory" in stderr.getvalue()
    assert "secret-not-for-output" not in stderr.getvalue()


def test_smoke_script_returns_nonzero_for_privacy_failure_without_leaking_value(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from apps.api.seawatch.historical.schema import VesselBaseline
    from scripts.smoke_gfw_historical import main

    _write_smoke_fixture(tmp_path)
    original = VesselBaseline.to_dict

    def leaking_payload(self: VesselBaseline) -> dict:
        payload = original(self)
        payload["mmsi"] = "416000001"
        return payload

    monkeypatch.setattr(VesselBaseline, "to_dict", leaking_payload)
    stdout = StringIO()
    stderr = StringIO()

    exit_code = main(
        environ={
            "SEAWATCH_DATA_ROOT": str(tmp_path),
            "SEAWATCH_IDENTITY_KEY": "secret-not-for-output",
        },
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code != 0
    assert stdout.getvalue() == ""
    assert "privacy" in stderr.getvalue().casefold()
    assert "416000001" not in stderr.getvalue()
    assert "secret-not-for-output" not in stderr.getvalue()
