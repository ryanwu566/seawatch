from __future__ import annotations

import logging

from fastapi.testclient import TestClient

from apps.api.seawatch.live import reset_live_runtime
from apps.api.seawatch.live.resilience import EdgeInputKind
from apps.api.seawatch.main import create_app


def teardown_function() -> None:
    reset_live_runtime()


def test_disabled_edge_health_is_normal_inactive_response(monkeypatch) -> None:
    monkeypatch.delenv("SEAWATCH_EDGE_INGEST", raising=False)
    monkeypatch.delenv("SEAWATCH_EDGE_REPLAY_ENABLED", raising=False)

    with TestClient(create_app()) as client:
        response = client.get("/edge/health")
        cloud = client.get("/live/vessels")

    assert response.status_code == 200
    assert response.json()["receiver_active"] is False
    assert response.json()["receiver_detected"] is False
    assert response.json()["input_kind"] == "disabled"
    assert cloud.status_code == 200


def test_synchronous_edge_start_failure_does_not_block_cloud_or_repeat_logs(
    monkeypatch, caplog
) -> None:
    monkeypatch.setenv("SEAWATCH_EDGE_INGEST", "true")
    monkeypatch.setenv("SEAWATCH_LIVE_INGEST", "false")
    calls = 0

    def fail_start(self) -> None:
        nonlocal calls
        calls += 1
        raise OSError("simulated bind failure")

    monkeypatch.setattr(
        "apps.api.seawatch.live.edge_ingest.EdgeAisConsumer.start", fail_start
    )
    caplog.set_level(logging.WARNING, logger="seawatch.main")

    with TestClient(create_app()) as client:
        assert client.get("/live/health").status_code == 200
        edge = client.get("/edge/health")

    assert calls == 1
    assert edge.status_code == 200
    assert edge.json()["receiver_active"] is False
    assert "simulated bind failure" in (edge.json()["last_error"] or "")
    assert sum("Edge AIS ingest" in record.message for record in caplog.records) == 1


def test_enabled_listener_with_no_messages_is_active_but_not_detected(monkeypatch) -> None:
    monkeypatch.setenv("SEAWATCH_EDGE_INGEST", "true")
    monkeypatch.setenv("SEAWATCH_LIVE_INGEST", "false")

    def simulate_bound_listener(self) -> None:
        self.health.receiver_active = True
        self.health.input_kind = EdgeInputKind.UDP

    monkeypatch.setattr(
        "apps.api.seawatch.live.edge_ingest.EdgeAisConsumer.start",
        simulate_bound_listener,
    )

    with TestClient(create_app()) as client:
        edge = client.get("/edge/health").json()
        assert client.get("/live/vessels").status_code == 200

    assert edge["receiver_active"] is True
    assert edge["receiver_detected"] is False
    assert edge["local_vessel_count"] == 0
