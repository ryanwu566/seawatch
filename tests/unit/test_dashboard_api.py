"""Offline tests for the SeaWatch Phase 4 read-only dashboard API.

These tests never rely on real local Phase 3B artifacts. They build a synthetic
ranking Parquet under a temporary ``SEAWATCH_DATA_ROOT`` so the suite runs fully
offline and deterministically in CI.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from apps.api.seawatch.main import create_app
from apps.api.seawatch.services import artifacts


def _reason(feature_name: str, group: str, percentile: float) -> dict:
    return {
        "reason_code": f"{group}_higher",
        "feature_group": group,
        "feature_name": feature_name,
        "observed_value": 14.2,
        "unit": "knots",
        "reference_percentile": percentile,
        "direction": "higher",
        "severity": 2.31,
        "message": f"{feature_name} is at a high percentile of the January 1 background.",
        "attribution_kind": "supporting_evidence",
    }


def _synthetic_frame() -> pd.DataFrame:
    reasons_a = json.dumps([_reason("sog_mean", "speed", 0.985)], sort_keys=True)
    reasons_b = json.dumps([_reason("turn_rate", "maneuver", 0.91)], sort_keys=True)
    return pd.DataFrame(
        {
            "track_id": ["trk-a", "trk-a", "trk-b"],
            "source_date": ["2024-01-03", "2024-01-03", "2024-01-03"],
            "window_id": ["w-001", "w-001", "w-002"],
            "method_id": ["isolation_forest", "robust_mad", "isolation_forest"],
            "review_priority_score": [87.4, 61.0, 42.5],
            "rank_within_date_method": [1, 2, 3],
            "shortlisted": [True, True, False],
            "review_status": ["unreviewed", "unreviewed", "unreviewed"],
            "observation_count": [118, 118, 54],
            "observed_duration_seconds": [3540.0, 3540.0, 1800.0],
            "max_gap_seconds": [120.0, 120.0, 300.0],
            "sog_valid_fraction": [0.99, 0.99, 0.87],
            "cog_valid_fraction": [0.98, 0.98, 0.80],
            "evidence_reasons": [reasons_a, reasons_b, reasons_b],
            # Identity columns that MUST be dropped defensively even if present.
            "mmsi": ["123456789", "123456789", "987654321"],
            "vessel_name": ["ALPHA", "ALPHA", "BETA"],
            "imo": ["IMO1", "IMO1", "IMO2"],
            "call_sign": ["AAA", "AAA", "BBB"],
        }
    )


@pytest.fixture
def client_with_artifacts(tmp_path: Path, monkeypatch) -> TestClient:
    ranking_dir = tmp_path / "data" / "processed" / "review_ranking"
    ranking_dir.mkdir(parents=True)
    _synthetic_frame().to_parquet(ranking_dir / "test_rankings.parquet", index=False)
    monkeypatch.setenv("SEAWATCH_DATA_ROOT", str(tmp_path))
    artifacts.reset_cache()
    yield TestClient(create_app())
    artifacts.reset_cache()


@pytest.fixture
def client_without_artifacts(tmp_path: Path, monkeypatch) -> TestClient:
    # Point at an empty root so no ranking artifact is found.
    empty_root = tmp_path / "empty"
    empty_root.mkdir()
    monkeypatch.setenv("SEAWATCH_DATA_ROOT", str(empty_root))
    artifacts.reset_cache()
    yield TestClient(create_app())
    artifacts.reset_cache()


def test_health_endpoint_returns_ok_payload(client_without_artifacts: TestClient) -> None:
    response = client_without_artifacts.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "seawatch-api"}


def test_alerts_schema_shape_and_content(client_with_artifacts: TestClient) -> None:
    response = client_with_artifacts.get("/alerts")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 3
    # Ordered by descending review priority.
    scores = [alert["ranking_score"] for alert in body["alerts"]]
    assert scores == sorted(scores, reverse=True)

    top = body["alerts"][0]
    assert set(top) >= {
        "alert_id",
        "track_id",
        "date",
        "ranking_score",
        "ranking_method",
        "rank",
        "shortlisted",
        "explanation_reasons",
    }
    assert top["alert_id"] == "2024-01-03__isolation_forest__trk-a__w-001"
    assert top["ranking_method"] == "isolation_forest"
    reason = top["explanation_reasons"][0]
    assert set(reason) >= {
        "reason_code",
        "feature_group",
        "feature_name",
        "observed_value",
        "unit",
        "reference_percentile",
        "direction",
        "severity",
        "message",
        "attribution_kind",
    }


def test_alert_detail_round_trip_and_not_found(client_with_artifacts: TestClient) -> None:
    listing = client_with_artifacts.get("/alerts").json()
    alert_id = listing["alerts"][0]["alert_id"]

    detail = client_with_artifacts.get(f"/alerts/{alert_id}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["alert_id"] == alert_id
    assert body["data_quality"]["observation_count"] == 118
    assert body["supporting_features"]
    assert body["review_status"] == "unreviewed"

    missing = client_with_artifacts.get("/alerts/does-not-exist")
    assert missing.status_code == 404


def test_shortlisted_only_filter(client_with_artifacts: TestClient) -> None:
    response = client_with_artifacts.get("/alerts", params={"shortlisted_only": "true"})
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 2
    assert all(alert["shortlisted"] for alert in body["alerts"])


def test_privacy_no_identity_fields_in_tracks_or_alerts(client_with_artifacts: TestClient) -> None:
    forbidden_tokens = {"mmsi", "vessel_name", "imo", "call_sign", "callsign", "shipname"}

    tracks_text = client_with_artifacts.get("/tracks").text.lower()
    alerts_text = client_with_artifacts.get("/alerts").text.lower()
    listing = client_with_artifacts.get("/alerts").json()
    detail_text = client_with_artifacts.get(f"/alerts/{listing['alerts'][0]['alert_id']}").text.lower()

    for token in forbidden_tokens:
        assert token not in tracks_text
        assert token not in alerts_text
        assert token not in detail_text

    # Identity values must not leak either.
    for value in ("123456789", "987654321", "alpha", "beta"):
        assert value not in tracks_text
        assert value not in alerts_text
        assert value not in detail_text


def test_terminology_avoids_prohibited_vocabulary(client_with_artifacts: TestClient) -> None:
    prohibited = ("threat", "hostile", "illegal")
    listing = client_with_artifacts.get("/alerts").json()
    detail_text = client_with_artifacts.get(f"/alerts/{listing['alerts'][0]['alert_id']}").text.lower()
    for word in prohibited:
        assert word not in detail_text


def test_missing_artifact_returns_503(client_without_artifacts: TestClient) -> None:
    assert client_without_artifacts.get("/tracks").status_code == 503
    assert client_without_artifacts.get("/alerts").status_code == 503
    assert client_without_artifacts.get("/alerts/anything").status_code == 503


def test_tracks_are_privacy_safe_and_deduplicated(client_with_artifacts: TestClient) -> None:
    response = client_with_artifacts.get("/tracks")
    assert response.status_code == 200
    body = response.json()
    # Two distinct (track_id, date, window_id) rows despite three ranking rows.
    assert body["count"] == 2
    for track in body["tracks"]:
        assert set(track) == {"track_id", "date", "duration", "observation_count"}
