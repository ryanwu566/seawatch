from __future__ import annotations

import json
from pathlib import Path

import joblib
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from apps.api.seawatch.api import detection as detection_api
from apps.api.seawatch.detection import historical_runtime
from apps.api.seawatch.detection import service as detection_service
from apps.api.seawatch.main import create_app


FORBIDDEN_VALUES = (
    "D:/private/runtime",
    "123456789",
    "gfw-vessel-sensitive-001",
    "super-secret-token",
)


def _write_valid_bundle(path: Path) -> Path:
    path.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "vesselId": "gfw-vessel-sensitive-001",
                "mmsi": "123456789",
                "mmsi_join_status": "unique_9digit_candidate",
            }
        ]
    ).to_parquet(path / "historical_baselines.parquet", index=False)
    pd.DataFrame(
        [{"vesselId": "gfw-vessel-sensitive-001", "presence_hours": 12}]
    ).to_parquet(path / "vessel_habits.parquet", index=False)
    pd.DataFrame(
        [
            {
                "cell_lat": 25.0,
                "cell_lon": 121.5,
                "observation_count": 1_200,
                "unique_vessel_count": 80,
                "observed_days": 40,
                "active_hour_buckets": 300,
                "cell_active_hour_fraction": 0.25,
                "avg_vessels_per_active_hour": 4.0,
                "observation_share_pct": 0.0036,
                "first_observed_utc": "2026-01-01T00:00:00Z",
                "last_observed_utc": "2026-09-29T23:00:00Z",
                "mmsi": "123456789",
                "shipName": "private ship name",
                "credential": "super-secret-token",
            },
            {
                "cell_lat": 24.9,
                "cell_lon": 121.4,
                "observation_count": 12,
                "unique_vessel_count": 4,
                "observed_days": 3,
                "active_hour_buckets": 6,
                "cell_active_hour_fraction": 0.0009,
                "avg_vessels_per_active_hour": 2.0,
                "observation_share_pct": 0.00004,
                "first_observed_utc": "2026-01-02T00:00:00Z",
                "last_observed_utc": "2026-01-04T00:00:00Z",
                "vesselId": "gfw-vessel-sensitive-001",
                "local_path": "D:/private/runtime",
            },
        ]
    ).to_parquet(path / "traffic_context.parquet", index=False)
    joblib.dump(
        {
            "spatial_context": {"traffic_cell_count": 2457},
            "coverage_context": {"dataset_hour_buckets": 6528},
            "identity_policy": {
                "mmsi_join_status_counts": {"unique_9digit_candidate": 66043}
            },
            "localPath": "D:/private/runtime",
            "credential": "super-secret-token",
        },
        path / "detection_context.joblib",
    )
    (path / "source_metadata.json").write_text(
        json.dumps(
            {
                "dataModel": "standardized_hourly_vessel_presence",
                "dateRange": {"start": "2026-01-01", "end": "2026-09-29"},
                "rowCount": 33_200_000,
                "uniqueVesselIdCount": 400_800,
                "localPath": "D:/private/runtime",
                "rawMmsi": "123456789",
                "gfwVesselId": "gfw-vessel-sensitive-001",
                "credential": "super-secret-token",
            }
        ),
        encoding="utf-8",
    )
    (path / "data_quality_report.json").write_text(
        json.dumps(
            {
                "localPath": "D:/private/runtime",
                "credential": "super-secret-token",
            }
        ),
        encoding="utf-8",
    )
    return path


def _client() -> TestClient:
    return TestClient(create_app())


def _assert_forbidden_values_absent(serialized: str) -> None:
    for value in FORBIDDEN_VALUES:
        assert value not in serialized


@pytest.fixture(autouse=True)
def _reset_history(monkeypatch) -> None:
    monkeypatch.setenv("SEAWATCH_WARM_DETECTION", "false")
    historical_runtime.clear_cache()
    yield
    historical_runtime.clear_cache()


def test_historical_endpoint_returns_safe_available_summary(
    monkeypatch, tmp_path: Path
) -> None:
    bundle = _write_valid_bundle(tmp_path / "runtime")
    monkeypatch.setenv("SEAWATCH_HISTORICAL_RUNTIME", str(bundle))
    monkeypatch.delenv("SEAWATCH_DATA_ROOT", raising=False)

    response = _client().get("/detection/historical")

    assert response.status_code == 200
    assert response.json() == {
        "available": True,
        "runtime": "SeaWatch_Runtime_Taiwan_2026_v2",
        "data_model": "standardized_hourly_vessel_presence",
        "date_range": {"start": "2026-01-01", "end": "2026-09-29"},
        "row_count": 33_200_000,
        "unique_vessel_count": 400_800,
        "traffic_cell_count": 2457,
        "dataset_hour_buckets": 6528,
        "mmsi_join_status_counts": {"unique_9digit_candidate": 66043},
    }
    _assert_forbidden_values_absent(response.text)


def test_historical_endpoint_returns_200_when_bundle_absent(monkeypatch) -> None:
    monkeypatch.delenv("SEAWATCH_HISTORICAL_RUNTIME", raising=False)
    monkeypatch.delenv("SEAWATCH_DATA_ROOT", raising=False)

    response = _client().get("/detection/historical")

    assert response.status_code == 200
    assert response.json() == {
        "available": False,
        "reason": "Historical context unavailable",
    }
    _assert_forbidden_values_absent(response.text)


def test_corrupt_bundle_degrades_without_path_or_exception_leak(
    monkeypatch, tmp_path: Path
) -> None:
    bundle = tmp_path / "gfw-vessel-sensitive-001" / "runtime"
    bundle.mkdir(parents=True)
    for filename in historical_runtime.REQUIRED_FILES:
        (bundle / filename).write_text("super-secret-token", encoding="utf-8")
    monkeypatch.setenv("SEAWATCH_HISTORICAL_RUNTIME", str(bundle))

    response = _client().get("/detection/historical")

    assert response.status_code == 200
    assert response.json() == {
        "available": False,
        "reason": "Historical context unavailable",
    }
    _assert_forbidden_values_absent(response.text)
    assert str(bundle) not in response.text
    assert "ArrowInvalid" not in response.text


def test_sensitive_nested_summary_values_degrade_without_leaking(
    monkeypatch, tmp_path: Path
) -> None:
    bundle = _write_valid_bundle(tmp_path / "runtime")
    metadata_path = bundle / "source_metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["dateRange"] = {
        "start": "2026-01-01",
        "end": "2026-09-29",
        "sourcePath": "D:/private/runtime",
        "credential": "super-secret-token",
    }
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    context_path = bundle / "detection_context.joblib"
    context = joblib.load(context_path)
    context["identity_policy"]["mmsi_join_status_counts"]["123456789"] = (
        "gfw-vessel-sensitive-001"
    )
    joblib.dump(context, context_path)
    monkeypatch.setenv("SEAWATCH_HISTORICAL_RUNTIME", str(bundle))

    response = _client().get("/detection/historical")

    assert response.status_code == 200
    assert response.json() == {
        "available": False,
        "reason": "Historical context unavailable",
    }
    _assert_forbidden_values_absent(response.text)


def test_malformed_decoded_summary_degrades_instead_of_serialization_failure(
    monkeypatch, tmp_path: Path
) -> None:
    bundle = _write_valid_bundle(tmp_path / "runtime")
    context_path = bundle / "detection_context.joblib"
    context = joblib.load(context_path)
    context["spatial_context"]["traffic_cell_count"] = pd.array([1, 2])
    joblib.dump(context, context_path)
    monkeypatch.setenv("SEAWATCH_HISTORICAL_RUNTIME", str(bundle))

    response = TestClient(create_app(), raise_server_exceptions=False).get(
        "/detection/historical"
    )

    assert response.status_code == 200
    assert response.json() == {
        "available": False,
        "reason": "Historical context unavailable",
    }
    _assert_forbidden_values_absent(response.text)


def test_historical_endpoint_never_initializes_live_or_scenario_runtime(
    monkeypatch,
) -> None:
    monkeypatch.delenv("SEAWATCH_HISTORICAL_RUNTIME", raising=False)
    monkeypatch.delenv("SEAWATCH_DATA_ROOT", raising=False)
    detection_service._service = None

    def unexpected_runtime_initialization():
        raise AssertionError("historical status must not initialize a runtime")

    monkeypatch.setattr(detection_api, "get_service", unexpected_runtime_initialization)
    monkeypatch.setattr(
        detection_api, "get_live_runtime", unexpected_runtime_initialization
    )

    response = _client().get("/detection/historical")

    assert response.status_code == 200
    assert detection_service._service is None
    _assert_forbidden_values_absent(response.text)


def test_historical_traffic_endpoint_returns_200_when_bundle_absent(
    monkeypatch,
) -> None:
    monkeypatch.delenv("SEAWATCH_HISTORICAL_RUNTIME", raising=False)
    monkeypatch.delenv("SEAWATCH_DATA_ROOT", raising=False)

    response = _client().get("/detection/historical/traffic")

    assert response.status_code == 200
    assert response.json() == {"available": False, "cells": []}


def test_historical_traffic_endpoint_returns_only_safe_aggregate_cells(
    monkeypatch, tmp_path: Path
) -> None:
    bundle = _write_valid_bundle(tmp_path / "runtime")
    monkeypatch.setenv("SEAWATCH_HISTORICAL_RUNTIME", str(bundle))
    monkeypatch.delenv("SEAWATCH_DATA_ROOT", raising=False)

    response = _client().get("/detection/historical/traffic")

    assert response.status_code == 200
    assert response.json() == {
        "available": True,
        "cells": [
            {
                "cell_lat": 25.0,
                "cell_lon": 121.5,
                "observation_count": 1200,
                "unique_vessel_count": 80,
                "observed_days": 40,
                "active_hour_buckets": 300,
                "cell_active_hour_fraction": 0.25,
                "avg_vessels_per_active_hour": 4.0,
            },
            {
                "cell_lat": 24.9,
                "cell_lon": 121.4,
                "observation_count": 12,
                "unique_vessel_count": 4,
                "observed_days": 3,
                "active_hour_buckets": 6,
                "cell_active_hour_fraction": 0.0009,
                "avg_vessels_per_active_hour": 2.0,
            },
        ],
    }
    assert len(response.json()["cells"]) == 2
    for cell in response.json()["cells"]:
        assert set(cell) == {
            "cell_lat",
            "cell_lon",
            "observation_count",
            "unique_vessel_count",
            "observed_days",
            "active_hour_buckets",
            "cell_active_hour_fraction",
            "avg_vessels_per_active_hour",
        }
        assert cell["cell_lat"] * 10 == round(cell["cell_lat"] * 10)
        assert cell["cell_lon"] * 10 == round(cell["cell_lon"] * 10)
    _assert_forbidden_values_absent(response.text)
    for forbidden_field in (
        "mmsi",
        "imo",
        "vesselId",
        "shipName",
        "local_path",
        "credential",
        "first_observed_utc",
        "last_observed_utc",
    ):
        assert forbidden_field not in response.text


def test_historical_traffic_endpoint_reuses_cached_compact_loader(
    monkeypatch, tmp_path: Path
) -> None:
    bundle = _write_valid_bundle(tmp_path / "runtime")
    (bundle / "raw_presence_observations.parquet").touch()
    monkeypatch.setenv("SEAWATCH_HISTORICAL_RUNTIME", str(bundle))
    opened: list[str] = []
    original = pd.read_parquet

    def record_read(path, *args, **kwargs):
        opened.append(Path(path).name)
        return original(path, *args, **kwargs)

    monkeypatch.setattr(pd, "read_parquet", record_read)
    client = _client()

    first = client.get("/detection/historical/traffic")
    second = client.get("/detection/historical/traffic")

    assert first.json() == second.json()
    assert opened.count("traffic_context.parquet") == 1
    assert "raw_presence_observations.parquet" not in opened


def test_historical_traffic_malformed_cell_degrades_without_leaking(
    monkeypatch, tmp_path: Path
) -> None:
    bundle = _write_valid_bundle(tmp_path / "runtime")
    traffic_path = bundle / "traffic_context.parquet"
    traffic = pd.read_parquet(traffic_path)
    traffic.loc[0, "cell_lat"] = float("inf")
    traffic.loc[1, "avg_vessels_per_active_hour"] = float("nan")
    traffic.to_parquet(traffic_path, index=False)
    monkeypatch.setenv("SEAWATCH_HISTORICAL_RUNTIME", str(bundle))

    response = _client().get("/detection/historical/traffic")

    assert response.status_code == 200
    assert response.json() == {"available": False, "cells": []}
    _assert_forbidden_values_absent(response.text)


def test_historical_traffic_endpoint_never_initializes_detection_runtime(
    monkeypatch,
) -> None:
    monkeypatch.delenv("SEAWATCH_HISTORICAL_RUNTIME", raising=False)
    monkeypatch.delenv("SEAWATCH_DATA_ROOT", raising=False)
    detection_service._service = None

    def unexpected_runtime_initialization():
        raise AssertionError("historical traffic must not initialize DetectionService")

    monkeypatch.setattr(detection_api, "get_service", unexpected_runtime_initialization)
    monkeypatch.setattr(
        detection_api, "get_live_runtime", unexpected_runtime_initialization
    )

    response = _client().get("/detection/historical/traffic")

    assert response.status_code == 200
    assert response.json() == {"available": False, "cells": []}
    assert detection_service._service is None
