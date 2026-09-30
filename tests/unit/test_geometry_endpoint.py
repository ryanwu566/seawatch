"""Offline tests for the read-only track geometry endpoint.

These build a synthetic Phase 1 observation Parquet under a temporary
``SEAWATCH_DATA_ROOT`` so the suite runs fully offline and never depends on real
processed artifacts.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from apps.api.seawatch.main import create_app
from apps.api.seawatch.services import geometry_service


def _observation_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            # Intentionally out of time order to prove the service sorts by time.
            "track_id": ["trk-a", "trk-a", "trk-a", "trk-b", "solo"],
            "base_date_time": pd.to_datetime(
                [
                    "2024-01-03T00:02:00Z",
                    "2024-01-03T00:00:00Z",
                    "2024-01-03T00:01:00Z",
                    "2024-01-03T00:00:00Z",
                    "2024-01-03T00:00:00Z",
                ],
                utc=True,
            ),
            "longitude": [-122.30, -122.40, -122.35, -122.10, -122.00],
            "latitude": [37.80, 37.70, 37.75, 37.60, 37.50],
            "sog": [1.0, 0.0, 0.5, 2.0, 0.0],
            "cog": [10.0, 20.0, 30.0, 40.0, 50.0],
            "heading": [11.0, 21.0, 31.0, 41.0, 51.0],
            "vessel_type": [70, 70, 70, 80, 90],
            # Identity columns that MUST be dropped defensively if ever present.
            "mmsi": ["111", "111", "111", "222", "333"],
            "vessel_name": ["ALPHA", "ALPHA", "ALPHA", "BETA", "GAMMA"],
        }
    )


@pytest.fixture
def client_with_geometry(tmp_path: Path, monkeypatch) -> TestClient:
    processed = tmp_path / "data" / "processed"
    processed.mkdir(parents=True)
    _observation_frame().to_parquet(processed / "noaa_ais_2024-01-03_sf_bay.parquet", index=False)
    monkeypatch.setenv("SEAWATCH_DATA_ROOT", str(tmp_path))
    geometry_service.reset_cache()
    yield TestClient(create_app())
    geometry_service.reset_cache()


@pytest.fixture
def client_without_artifacts(tmp_path: Path, monkeypatch) -> TestClient:
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setenv("SEAWATCH_DATA_ROOT", str(empty))
    geometry_service.reset_cache()
    yield TestClient(create_app())
    geometry_service.reset_cache()


def test_geometry_returns_time_ordered_linestring(client_with_geometry: TestClient) -> None:
    response = client_with_geometry.get("/tracks/trk-a/geometry")
    assert response.status_code == 200
    body = response.json()
    assert body["track_id"] == "trk-a"
    assert body["geometry"]["type"] == "LineString"
    # Ordered by observation time: 00:00, 00:01, 00:02.
    assert body["geometry"]["coordinates"] == [
        [-122.40, 37.70],
        [-122.35, 37.75],
        [-122.30, 37.80],
    ]


def test_geometry_privacy_no_identifiers_in_response(client_with_geometry: TestClient) -> None:
    text = client_with_geometry.get("/tracks/trk-a/geometry").text.lower()
    for token in ("mmsi", "vessel_name", "imo", "call_sign", "callsign"):
        assert token not in text
    for value in ("alpha", "beta", "gamma", "111", "222", "333"):
        assert value not in text


def test_geometry_unknown_track_returns_404(client_with_geometry: TestClient) -> None:
    assert client_with_geometry.get("/tracks/does-not-exist/geometry").status_code == 404


def test_geometry_single_point_track_returns_404(client_with_geometry: TestClient) -> None:
    # "solo" has a single observation and cannot form a LineString.
    assert client_with_geometry.get("/tracks/solo/geometry").status_code == 404


def test_geometry_missing_artifact_returns_503(client_without_artifacts: TestClient) -> None:
    assert client_without_artifacts.get("/tracks/trk-a/geometry").status_code == 503
