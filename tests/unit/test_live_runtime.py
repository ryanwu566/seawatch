from __future__ import annotations

import logging
import asyncio
import threading
import time
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from apps.api.seawatch import live as live_pkg
from apps.api.seawatch.live.runtime import (
    CloudLiveState,
    LiveRuntime,
    get_live_runtime,
    reset_live_runtime,
)
from apps.api.seawatch.live.datalastic import (
    DatalasticClient,
    DatalasticStatus,
    ProviderError,
    ProviderErrorCategory,
)
from apps.api.seawatch.main import create_app


def teardown_function() -> None:
    reset_live_runtime()


def test_runtime_owns_one_process_wide_cloud_store_and_consumer() -> None:
    first = get_live_runtime()
    second = get_live_runtime()

    assert isinstance(first, LiveRuntime)
    assert isinstance(first.cloud, CloudLiveState)
    assert first is second
    assert first.cloud.consumer.store is first.cloud.store
    assert first.edge.consumer.store is first.edge.store
    assert first.edge.store is not first.cloud.store


def test_compatibility_getters_return_cloud_owned_objects() -> None:
    runtime = get_live_runtime()

    assert live_pkg.get_store() is runtime.cloud.store
    assert live_pkg.get_consumer() is runtime.cloud.consumer


def test_compatibility_reset_replaces_runtime_store_and_consumer() -> None:
    original = get_live_runtime()

    live_pkg.reset_live_state()
    replacement = get_live_runtime()

    assert replacement is not original
    assert replacement.cloud.store is not original.cloud.store
    assert replacement.cloud.consumer is not original.cloud.consumer


def test_startup_does_not_start_cloud_consumer_when_disabled(
    monkeypatch,
) -> None:
    starts: list[object] = []
    monkeypatch.setenv("SEAWATCH_LIVE_INGEST", "false")
    monkeypatch.setattr(
        "apps.api.seawatch.live.ingest.AisIngestConsumer.start",
        lambda self: starts.append(self),
    )

    with TestClient(create_app()):
        pass

    assert starts == []


def test_startup_starts_and_stops_exact_cloud_consumer_when_enabled(
    monkeypatch,
) -> None:
    starts: list[object] = []
    stops: list[object] = []
    monkeypatch.setenv("SEAWATCH_LIVE_INGEST", "true")
    monkeypatch.setattr(
        "apps.api.seawatch.live.ingest.AisIngestConsumer.start",
        lambda self: starts.append(self),
    )

    async def record_stop(consumer) -> None:
        stops.append(consumer)

    monkeypatch.setattr(
        "apps.api.seawatch.live.ingest.AisIngestConsumer.stop",
        record_stop,
    )

    runtime = get_live_runtime()
    with TestClient(create_app()):
        assert starts == [runtime.cloud.consumer]

    assert stops == [runtime.cloud.consumer]


def test_live_provider_start_failure_warns_but_api_still_runs(
    monkeypatch,
    caplog,
) -> None:
    monkeypatch.setenv("SEAWATCH_LIVE_INGEST", "true")

    def fail_to_start(_consumer) -> None:
        raise OSError("provider unreachable")

    monkeypatch.setattr(
        "apps.api.seawatch.live.ingest.AisIngestConsumer.start",
        fail_to_start,
    )

    with caplog.at_level(logging.WARNING, logger="seawatch.main"):
        with TestClient(create_app()) as client:
            response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert "Failed to start live AIS ingest" in caplog.text


def test_runtime_configures_request_driven_datalastic_without_replacing_openwaters(
    monkeypatch,
) -> None:
    monkeypatch.setenv("DATALASTIC_API_KEY", "runtime-secret")
    runtime = get_live_runtime()

    assert runtime.datalastic_config.configured is True
    assert runtime.datalastic_client is not None
    assert runtime.area_scan_service is not None
    assert runtime.cloud.consumer.provider.name == "open_waters"
    assert "runtime-secret" not in repr(runtime.datalastic_config)


def test_datalastic_status_probe_is_non_blocking_and_cancelled_on_shutdown(
    monkeypatch,
) -> None:
    monkeypatch.setenv("DATALASTIC_API_KEY", "runtime-secret")
    started = threading.Event()
    cancelled = threading.Event()

    async def slow_stat(_client):
        started.set()
        try:
            await asyncio.sleep(60)
        finally:
            cancelled.set()

    monkeypatch.setattr(DatalasticClient, "stat", slow_stat)

    before = time.monotonic()
    with TestClient(create_app()) as client:
        assert started.wait(timeout=2)
        response = client.get("/health")
        assert time.monotonic() - before < 5

    assert response.status_code == 200
    assert cancelled.wait(timeout=2)


def test_health_endpoints_read_one_cached_datalastic_probe_without_new_traffic(
    monkeypatch,
) -> None:
    monkeypatch.setenv("DATALASTIC_API_KEY", "runtime-secret")
    calls = 0
    completed = threading.Event()

    async def successful_stat(_client):
        nonlocal calls
        calls += 1
        completed.set()
        return DatalasticStatus(
            configured=True,
            reachable=True,
            key_status="valid",
            addons=False,
            requests_remaining=321,
            rate_limit_remaining=87,
            last_success_at=datetime(2026, 10, 3, tzinfo=timezone.utc),
            last_error_category=None,
        )

    monkeypatch.setattr(DatalasticClient, "stat", successful_stat)

    with TestClient(create_app()) as client:
        assert completed.wait(timeout=2)
        live_one = client.get("/live/health")
        live_two = client.get("/live/health")
        global_health = client.get("/health")

    assert calls == 1
    assert global_health.status_code == 200
    assert live_one.json()["provider"] == "datalastic"
    assert live_two.json()["provider_status"] == {
        "provider": "datalastic",
        "configured": True,
        "reachable": True,
        "key_status": "valid",
        "addons": False,
        "requests_remaining": 321,
        "rate_limit_remaining": 87,
        "last_success_at": "2026-10-03T00:00:00+00:00",
        "last_error_category": None,
    }
    assert "runtime-secret" not in live_two.text


def test_failed_datalastic_probe_degrades_without_blocking_api_or_leaking(
    monkeypatch,
    caplog,
) -> None:
    monkeypatch.setenv("DATALASTIC_API_KEY", "runtime-secret")
    completed = threading.Event()

    async def failed_stat(_client):
        completed.set()
        raise ProviderError(ProviderErrorCategory.CONNECTION)

    monkeypatch.setattr(DatalasticClient, "stat", failed_stat)

    with caplog.at_level(logging.WARNING, logger="seawatch.main"):
        with TestClient(create_app()) as client:
            assert completed.wait(timeout=2)
            response = client.get("/live/health")
            global_health = client.get("/health")

    assert global_health.status_code == 200
    assert response.json()["provider"] == "datalastic"
    assert response.json()["provider_status"]["reachable"] is False
    assert response.json()["provider_status"]["last_error_category"] == "connection"
    assert "runtime-secret" not in response.text
    assert "runtime-secret" not in caplog.text
