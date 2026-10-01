from __future__ import annotations

from fastapi.testclient import TestClient

from apps.api.seawatch import live as live_pkg
from apps.api.seawatch.live.runtime import (
    CloudLiveState,
    LiveRuntime,
    get_live_runtime,
    reset_live_runtime,
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
