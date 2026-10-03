from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from apps.api.seawatch.live.identity import VesselIdentityRegistry


def _gfw_directory(root: Path) -> Path:
    directory = root / "ais" / "historical" / "processed" / "daily"
    directory.mkdir(parents=True)
    return directory


def _write_sufficient_history(
    root: Path,
    *,
    mmsi: object = "416000001",
    unjoinable_per_day: int = 0,
) -> None:
    directory = _gfw_directory(root)
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
                    "mmsi": mmsi,
                }
            )
        for excluded in range(unjoinable_per_day):
            rows.append(
                {
                    "date": (start + timedelta(days=day, hours=8 + excluded)).strftime(
                        "%Y-%m-%d %H:%M"
                    ),
                    "lat": 23.0,
                    "lon": 121.0,
                    "vesselId": f"unjoinable-{day}-{excluded}",
                    "mmsi": None,
                }
            )
        pq.write_table(
            pa.Table.from_pylist(rows),
            directory / f"gfw_taiwan_2026-09-{day + 1:02d}.parquet",
        )


def test_gfw_directory_is_derived_from_environment_data_root(tmp_path: Path) -> None:
    from apps.api.seawatch.historical.pipeline import resolve_gfw_parquet_dir

    resolved = resolve_gfw_parquet_dir({"SEAWATCH_DATA_ROOT": str(tmp_path)})

    assert resolved == tmp_path / "ais" / "historical" / "processed" / "daily"


def test_pipeline_fails_closed_without_shared_identity_configuration(
    tmp_path: Path,
) -> None:
    from apps.api.seawatch.historical.pipeline import (
        HistoricalIdentityUnavailableError,
        build_gfw_baselines,
    )

    with pytest.raises(HistoricalIdentityUnavailableError, match="IDENTITY_KEY"):
        build_gfw_baselines(environ={"SEAWATCH_DATA_ROOT": str(tmp_path)})


def test_pipeline_uses_configured_live_identity_key_without_gfw_token(
    tmp_path: Path,
) -> None:
    from apps.api.seawatch.historical.pipeline import build_gfw_baselines

    _write_sufficient_history(tmp_path)
    environ = {
        "SEAWATCH_DATA_ROOT": str(tmp_path),
        "SEAWATCH_IDENTITY_KEY": "shared-live-history-key",
    }

    baselines = build_gfw_baselines(environ=environ)

    expected = VesselIdentityRegistry(
        "shared-live-history-key"
    ).public_id_for_mmsi(416000001)
    assert list(baselines) == [expected]
    assert baselines[expected].sufficient is True


def test_pipeline_accepts_the_process_live_identity_registry(tmp_path: Path) -> None:
    from apps.api.seawatch.historical.pipeline import build_gfw_baselines

    _write_sufficient_history(tmp_path)
    registry = VesselIdentityRegistry("process-live-key")

    baselines = build_gfw_baselines(
        environ={"SEAWATCH_DATA_ROOT": str(tmp_path)},
        identity_registry=registry,
    )

    expected = registry.public_id_for_mmsi(416000001)
    assert list(baselines) == [expected]


def test_records_without_usable_mmsi_are_never_joined_to_live_vessels(
    tmp_path: Path,
) -> None:
    from apps.api.seawatch.historical.pipeline import build_gfw_baselines

    _write_sufficient_history(tmp_path, mmsi="unknown")

    baselines = build_gfw_baselines(
        environ={
            "SEAWATCH_DATA_ROOT": str(tmp_path),
            "SEAWATCH_IDENTITY_KEY": "shared-live-history-key",
        }
    )

    assert baselines == {}


def test_pipeline_result_reports_aggregate_counts_and_keeps_legacy_return_type(
    tmp_path: Path,
) -> None:
    from apps.api.seawatch.historical.pipeline import (
        GfwHistoricalPipelineResult,
        build_gfw_baselines,
        run_gfw_historical_pipeline,
    )

    _write_sufficient_history(tmp_path, unjoinable_per_day=1)
    environ = {
        "SEAWATCH_DATA_ROOT": str(tmp_path),
        "SEAWATCH_IDENTITY_KEY": "shared-live-history-key",
    }

    result = run_gfw_historical_pipeline(environ=environ)
    legacy = build_gfw_baselines(environ=environ)

    assert isinstance(result, GfwHistoricalPipelineResult)
    assert result.diagnostics.discovered_parquet_file_count == 5
    assert result.diagnostics.observations_considered == 20
    assert result.diagnostics.observations_joinable_by_valid_mmsi == 15
    assert result.diagnostics.observations_excluded_from_live_identity_join == 5
    assert result.diagnostics.grouped_vessel_count == 1
    assert result.diagnostics.vessel_baseline_count == 1
    assert result.diagnostics.sufficient_baseline_count == 1
    assert result.diagnostics.insufficient_baseline_count == 0
    assert isinstance(legacy, dict)
    assert legacy == result.baselines


@pytest.mark.parametrize(
    "payload",
    [
        {"vessel_key": "v_opaque", "mmsi": "416000001"},
        {"vessel_key": "v_opaque", "note": "raw-gfw-vessel-id"},
    ],
)
def test_baseline_privacy_audit_rejects_leaks_without_echoing_the_value(
    payload: dict[str, object],
) -> None:
    from apps.api.seawatch.historical.pipeline import (
        HistoricalBaselinePrivacyError,
        assert_public_baselines_private,
    )

    class SerializedBaseline:
        def to_dict(self) -> dict[str, object]:
            return payload

    with pytest.raises(HistoricalBaselinePrivacyError) as caught:
        assert_public_baselines_private(
            {"v_opaque": SerializedBaseline()},  # type: ignore[dict-item]
            raw_identifiers={"416000001", "raw-gfw-vessel-id"},
        )

    message = str(caught.value)
    assert "416000001" not in message
    assert "raw-gfw-vessel-id" not in message
