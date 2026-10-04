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
        [{"cell_lat": 25.0, "cell_lon": 121.5, "presence": 1}]
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
