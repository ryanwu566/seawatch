from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import httpx

from apps.api.seawatch.live.area_scan import AreaScanRequest
from apps.api.seawatch.live.area_scan_access import mint_area_scan_capability
from apps.api.seawatch.live.datalastic import (
    DatalasticClient,
    DatalasticStatus,
    DatalasticStatusCache,
    ProviderError,
    ProviderErrorCategory,
    refresh_datalastic_status,
)
from apps.api.seawatch.live.runtime import get_live_runtime, reset_live_runtime
from apps.api.seawatch.main import create_app


TEST_SIGNING_KEY = "status-refresh-signing-secret-at-least-32-bytes"
REFRESH_PATH = "/live/area-scan/provider-status/refresh"
GEOMETRY = AreaScanRequest.model_validate(
    {
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [[120.0, 22.0], [120.1, 22.0], [120.1, 22.1], [120.0, 22.0]]
            ],
        }
    }
)


class _AreaProvider:
    def __init__(self) -> None:
        self.calls = 0

    async def scan(self, _queries):
        self.calls += 1
        return ()


def _configured_runtime(monkeypatch):
    monkeypatch.setenv("DATALASTIC_API_KEY", "provider-secret-never-return")
    monkeypatch.setenv("SEAWATCH_AREA_SCAN_SIGNING_KEY", TEST_SIGNING_KEY)
    monkeypatch.setenv("SEAWATCH_LIVE_INGEST", "false")
    reset_live_runtime()
    return get_live_runtime()


def _auth_headers(runtime) -> dict[str, str]:
    return {
        "Authorization": (
            "Bearer " + mint_area_scan_capability(runtime.area_scan_access)
        )
    }


def _healthy_status() -> DatalasticStatus:
    return DatalasticStatus(
        configured=True,
        reachable=True,
        key_status="valid",
        addons=True,
        requests_remaining=4321,
        rate_limit_remaining=57,
        last_success_at=datetime(2026, 10, 4, 8, 30, tzinfo=timezone.utc),
        last_error_category=None,
    )


async def _post_refresh(runtime, *, headers: dict[str, str] | None = None):
    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://localhost",
    ) as client:
        return await client.post(REFRESH_PATH, headers=headers)


def _close_runtime(runtime) -> None:
    if runtime.datalastic_client is not None:
        asyncio.run(runtime.datalastic_client.aclose())
    reset_live_runtime()


def test_authorized_refresh_calls_only_provider_stat_once(monkeypatch) -> None:
    runtime = _configured_runtime(monkeypatch)
    area_provider = _AreaProvider()
    runtime.area_scan_service.set_provider(area_provider)
    stat_calls = 0
    vessel_calls = 0

    async def stat(_client):
        nonlocal stat_calls
        stat_calls += 1
        return _healthy_status()

    async def vessels_in_radius(_client, *_args, **_kwargs):
        nonlocal vessel_calls
        vessel_calls += 1
        raise AssertionError("provider Area Scan must not run during status refresh")

    monkeypatch.setattr(DatalasticClient, "stat", stat)
    monkeypatch.setattr(DatalasticClient, "vessels_in_radius", vessels_in_radius)

    try:
        response = asyncio.run(_post_refresh(runtime, headers=_auth_headers(runtime)))

        assert response.status_code == 200
        assert stat_calls == 1
        assert vessel_calls == 0
        assert area_provider.calls == 0
        assert response.json() == {
            "provider": "datalastic",
            "configured": True,
            "reachable": True,
            "key_status": "valid",
            "addons": True,
            "requests_remaining": 4321,
            "rate_limit_remaining": 57,
            "last_success_at": "2026-10-04T08:30:00+00:00",
            "last_error_category": None,
        }
    finally:
        _close_runtime(runtime)


def test_unauthorized_refresh_makes_zero_provider_calls(monkeypatch) -> None:
    runtime = _configured_runtime(monkeypatch)
    stat_calls = 0

    async def stat(_client):
        nonlocal stat_calls
        stat_calls += 1
        return _healthy_status()

    monkeypatch.setattr(DatalasticClient, "stat", stat)

    try:
        response = asyncio.run(_post_refresh(runtime))

        assert response.status_code == 401
        assert stat_calls == 0
    finally:
        _close_runtime(runtime)


def test_rate_limited_refresh_makes_zero_provider_calls(monkeypatch) -> None:
    runtime = _configured_runtime(monkeypatch)
    stat_calls = 0

    async def stat(_client):
        nonlocal stat_calls
        stat_calls += 1
        return _healthy_status()

    monkeypatch.setattr(DatalasticClient, "stat", stat)
    for _ in range(runtime.area_scan_access.max_scans_per_window):
        runtime.area_scan_admission.authorize(provider_requests=0)

    try:
        response = asyncio.run(_post_refresh(runtime, headers=_auth_headers(runtime)))

        assert response.status_code == 429
        assert response.json()["detail"] == "Provider status refresh limit reached"
        assert stat_calls == 0
    finally:
        _close_runtime(runtime)


def test_transient_failure_recovers_cached_readiness_without_restart(monkeypatch) -> None:
    runtime = _configured_runtime(monkeypatch)
    runtime.datalastic_status.record_failure(ProviderErrorCategory.CONNECTION)

    async def stat(_client):
        return _healthy_status()

    monkeypatch.setattr(DatalasticClient, "stat", stat)

    try:
        assert runtime.datalastic_status.snapshot().reachable is False

        response = asyncio.run(_post_refresh(runtime, headers=_auth_headers(runtime)))

        assert response.status_code == 200
        refreshed = runtime.datalastic_status.snapshot()
        assert refreshed.reachable is True
        assert refreshed.key_status == "valid"
        assert refreshed.last_error_category is None
        assert response.json()["reachable"] is True
    finally:
        _close_runtime(runtime)


def test_invalid_key_refresh_remains_unavailable(monkeypatch) -> None:
    runtime = _configured_runtime(monkeypatch)

    async def stat(_client):
        raise ProviderError(ProviderErrorCategory.AUTHENTICATION)

    monkeypatch.setattr(DatalasticClient, "stat", stat)

    try:
        response = asyncio.run(_post_refresh(runtime, headers=_auth_headers(runtime)))

        assert response.status_code == 200
        assert response.json()["reachable"] is False
        assert response.json()["key_status"] == "invalid"
        assert response.json()["last_error_category"] == "authentication"
    finally:
        _close_runtime(runtime)


def test_provider_failure_returns_safe_degraded_status(monkeypatch) -> None:
    runtime = _configured_runtime(monkeypatch)
    upstream_secret = "raw-upstream-secret-response-body"

    async def stat(_client):
        raise RuntimeError(upstream_secret)

    monkeypatch.setattr(DatalasticClient, "stat", stat)

    try:
        response = asyncio.run(_post_refresh(runtime, headers=_auth_headers(runtime)))

        assert response.status_code == 200
        assert response.json()["reachable"] is False
        assert response.json()["last_error_category"] == "connection"
        assert upstream_secret not in response.text
        assert "provider-secret-never-return" not in response.text
    finally:
        _close_runtime(runtime)


def test_refresh_preserves_prior_area_scan_cache(monkeypatch) -> None:
    runtime = _configured_runtime(monkeypatch)
    area_provider = _AreaProvider()
    runtime.area_scan_service.set_provider(area_provider)

    async def stat(_client):
        return _healthy_status()

    monkeypatch.setattr(DatalasticClient, "stat", stat)

    try:
        before = asyncio.run(runtime.area_scan_service.scan(GEOMETRY))
        response = asyncio.run(_post_refresh(runtime, headers=_auth_headers(runtime)))
        after = asyncio.run(runtime.area_scan_service.scan(GEOMETRY))

        assert response.status_code == 200
        assert area_provider.calls == 1
        assert before.cached is False
        assert after.cached is True
        assert after.scanned_at == before.scanned_at
    finally:
        _close_runtime(runtime)


def test_refresh_does_not_enable_continuous_live_ingest(monkeypatch) -> None:
    runtime = _configured_runtime(monkeypatch)

    async def stat(_client):
        return _healthy_status()

    monkeypatch.setattr(DatalasticClient, "stat", stat)

    async def scenario():
        transport = httpx.ASGITransport(app=create_app())
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://localhost",
        ) as client:
            refreshed = await client.post(REFRESH_PATH, headers=_auth_headers(runtime))
            health = await client.get("/live/health")
            return refreshed, health

    try:
        refreshed, health = asyncio.run(scenario())

        assert refreshed.json()["reachable"] is True
        assert health.json()["provider_status"]["reachable"] is True
        assert health.json()["live_ingest_enabled"] is False
        assert health.json()["mode"] == "NO_LIVE_SOURCE"
    finally:
        _close_runtime(runtime)


def test_older_probe_failure_cannot_overwrite_newer_success() -> None:
    cache = DatalasticStatusCache(configured=True)
    first_started = asyncio.Event()
    release_first = asyncio.Event()

    class OverlappingStatusClient:
        def __init__(self) -> None:
            self.calls = 0

        async def stat(self):
            self.calls += 1
            if self.calls == 1:
                first_started.set()
                await release_first.wait()
                raise ProviderError(ProviderErrorCategory.CONNECTION)
            return _healthy_status()

    async def scenario() -> None:
        client = OverlappingStatusClient()
        older = asyncio.create_task(refresh_datalastic_status(client, cache))
        await first_started.wait()
        newer = asyncio.create_task(refresh_datalastic_status(client, cache))

        newer_status = await newer
        release_first.set()
        older_status = await older

        assert client.calls == 2
        assert newer_status.reachable is True
        assert older_status.reachable is True
        assert cache.snapshot().reachable is True
        assert cache.snapshot().last_error_category is None

    asyncio.run(scenario())
