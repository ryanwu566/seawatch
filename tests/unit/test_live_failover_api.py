from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from apps.api.seawatch.live.resilience import EdgeInputKind
from apps.api.seawatch.live.runtime import get_live_runtime, reset_live_runtime
from apps.api.seawatch.live.schema import LiveVesselObservation
from apps.api.seawatch.main import create_app


NOW = datetime(2026, 10, 1, tzinfo=timezone.utc)


def teardown_function() -> None:
    reset_live_runtime()


def _observation(key: str, source: str, mmsi: int) -> LiveVesselObservation:
    return LiveVesselObservation(
        provider_id=key,
        latitude=22.5,
        longitude=120.25,
        observed_at=NOW,
        received_at=NOW,
        source=source,
        mmsi=mmsi,
    )


def test_resilience_status_and_live_health_are_additive_for_cloud(monkeypatch) -> None:
    monkeypatch.setenv("SEAWATCH_IDENTITY_KEY", "test-key")
    runtime = get_live_runtime()
    runtime.cloud.store.update(_observation("raw-cloud-key", "aishub", 416000001))

    with TestClient(create_app()) as client:
        status = client.get("/resilience/status")
        health = client.get("/live/health")

    assert status.status_code == 200
    assert status.json()["mode"] == "CLOUD_LIVE"
    assert status.json()["coverage"] == "taiwan_wide_network_feed"
    assert status.json()["cloud"]["fresh"] is True
    assert status.json()["edge"]["fresh"] is False
    assert status.json()["internet_available"] is True
    assert set(health.json()) >= {
        "status",
        "provider",
        "connected",
        "last_message_at",
        "message_age_seconds",
        "vessel_count",
        "reconnect_attempts",
        "last_error",
        "mode",
        "coverage",
        "simulated",
        "cloud",
        "edge",
    }


def test_edge_mode_selects_only_edge_live_data_and_preserves_privacy(monkeypatch) -> None:
    monkeypatch.setenv("SEAWATCH_IDENTITY_KEY", "test-key")
    runtime = get_live_runtime()
    runtime.edge.store.update(_observation("raw-edge-key", "edge_ais", 416000002))
    runtime.edge.consumer.health.input_kind = EdgeInputKind.UDP
    runtime.edge.consumer.health.receiver_active = True
    runtime.edge.consumer.health.receiver_detected = True
    runtime.edge.consumer._last_valid_monotonic = runtime.edge.store.last_message_monotonic()

    with TestClient(create_app()) as client:
        vessels = client.get("/live/vessels")
        status = client.get("/resilience/status")

    assert status.json()["mode"] == "EDGE_LIVE"
    feature = vessels.json()["features"][0]
    assert feature["properties"]["observation_origin"] == "edge_rf"
    assert feature["properties"]["display_state"] == "live"
    assert feature["properties"]["active_source"] is True
    assert feature["properties"]["coverage"] == "local_rf"
    serialized = vessels.text.lower()
    for forbidden in ("mmsi", "416000002", "raw-edge-key", "imo", "callsign"):
        assert forbidden not in serialized


def test_replay_is_always_simulated_and_never_labeled_live_rf(monkeypatch) -> None:
    monkeypatch.setenv("SEAWATCH_IDENTITY_KEY", "test-key")
    runtime = get_live_runtime()
    runtime.edge.store.update(_observation("replay-key", "edge_replay", 416000003))
    runtime.edge.consumer.health.input_kind = EdgeInputKind.REPLAY
    runtime.edge.consumer.health.receiver_active = True
    runtime.edge.consumer.health.receiver_detected = True
    runtime.edge.consumer._last_valid_monotonic = runtime.edge.store.last_message_monotonic()

    with TestClient(create_app()) as client:
        status = client.get("/resilience/status").json()
        feature = client.get("/live/vessels").json()["features"][0]

    assert status["mode"] == "EDGE_REPLAY"
    assert status["simulated"] is True
    assert feature["properties"]["observation_origin"] == "edge_replay"
