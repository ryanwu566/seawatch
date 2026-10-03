from __future__ import annotations

import asyncio
import logging
from datetime import datetime

import httpx
import pytest

from apps.api.seawatch.live.datalastic import (
    DatalasticAreaScanProvider,
    DatalasticClient,
    DatalasticConfig,
    DatalasticStatusCache,
    ProviderError,
    ProviderErrorCategory,
    RadiusQuery,
)


SECRET = "dl_test_secret_never_expose"
BASE_URL = "https://provider.test/api/v0/"


def _stat_payload(*, success: bool = True) -> dict:
    return {
        "data": {
            "user_id": SECRET,
            "key_status": "Valid",
            "requests_made": 12,
            "requests_remaining": 988,
            "addons": True,
        },
        "meta": {"duration": 0.01, "endpoint": "/api/v0/stat", "success": success},
    }


def _radius_payload() -> dict:
    return {
        "data": {
            "point": {"lat": 22.5, "lon": 120.25, "radius": 2},
            "total": 1,
            "vessels": [
                {
                    "uuid": "provider-uuid-1",
                    "name": "REAL VESSEL",
                    "mmsi": "416000001",
                    "imo": "9876543",
                    "eni": None,
                    "country_iso": "TW",
                    "type": "Cargo",
                    "type_specific": "Container Ship",
                    "lat": 22.51,
                    "lon": 120.26,
                    "speed": 8.4,
                    "course": 181.2,
                    "heading": 180,
                    "navigation_status": "Under way using engine",
                    "destination": "KHH",
                    "last_position_epoch": 1790992800,
                    "last_position_UTC": "2026-10-03T02:00:00Z",
                    "eta_epoch": None,
                    "eta_UTC": None,
                    "distance": 0.8,
                }
            ],
        },
        "meta": {
            "duration": 0.02,
            "endpoint": "/api/v0/vessel_inradius",
            "success": True,
        },
    }


def _client(handler, **kwargs) -> DatalasticClient:
    return DatalasticClient(
        DatalasticConfig(api_key=SECRET, base_url=BASE_URL),
        transport=httpx.MockTransport(handler),
        **kwargs,
    )


def test_stat_uses_header_auth_and_discards_user_id() -> None:
    async def scenario() -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            assert request.url == "https://provider.test/api/v0/stat"
            assert request.headers["x-api-key"] == SECRET
            assert SECRET not in str(request.url)
            return httpx.Response(
                200,
                json=_stat_payload(),
                headers={"X-Ratelimit-Remaining": "577"},
            )

        client = _client(handler)
        try:
            status = await client.stat()
        finally:
            await client.aclose()

        assert status.configured is True
        assert status.reachable is True
        assert status.key_status == "valid"
        assert status.addons is True
        assert status.requests_remaining == 988
        assert status.rate_limit_remaining == 577
        assert status.last_success_at is not None
        assert "user_id" not in status.to_public_dict()
        assert SECRET not in repr(status)

    asyncio.run(scenario())


def test_vessel_inradius_parses_typed_provider_vessel() -> None:
    async def scenario() -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            assert dict(request.url.params) == {
                "lat": "22.5",
                "lon": "120.25",
                "radius": "2.0",
            }
            return httpx.Response(200, json=_radius_payload())

        client = _client(handler)
        try:
            vessels = await client.vessels_in_radius(
                RadiusQuery(latitude=22.5, longitude=120.25, radius_nm=2.0)
            )
        finally:
            await client.aclose()

        assert len(vessels) == 1
        vessel = vessels[0]
        assert vessel.uuid == "provider-uuid-1"
        assert vessel.mmsi == 416000001
        assert vessel.imo == 9876543
        assert vessel.latitude == 22.51
        assert vessel.longitude == 120.26
        assert vessel.speed_knots == 8.4
        assert vessel.observed_at == datetime.fromisoformat("2026-10-03T02:00:00+00:00")

    asyncio.run(scenario())


def test_vessel_inradius_preserves_missing_provider_timestamp_as_unknown() -> None:
    async def scenario() -> None:
        payload = _radius_payload()
        payload["data"]["vessels"][0]["last_position_UTC"] = None
        payload["data"]["vessels"][0]["last_position_epoch"] = None

        async def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=payload)

        client = _client(handler)
        try:
            vessels = await client.vessels_in_radius(
                RadiusQuery(latitude=22.5, longitude=120.25, radius_nm=2.0)
            )
        finally:
            await client.aclose()

        assert vessels[0].observed_at is None

    asyncio.run(scenario())


def test_fractional_mmsi_is_rejected_instead_of_truncated() -> None:
    async def scenario() -> None:
        payload = _radius_payload()
        payload["data"]["vessels"][0]["mmsi"] = 416000001.5

        async def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=payload)

        client = _client(handler)
        try:
            with pytest.raises(ProviderError) as raised:
                await client.vessels_in_radius(RadiusQuery(22.5, 120.25, 2.0))
        finally:
            await client.aclose()

        assert raised.value.category is ProviderErrorCategory.MALFORMED_RESPONSE

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("status_code", "category"),
    [
        (401, ProviderErrorCategory.AUTHENTICATION),
        (403, ProviderErrorCategory.AUTHENTICATION),
        (402, ProviderErrorCategory.QUOTA_EXHAUSTED),
        (429, ProviderErrorCategory.RATE_LIMITED),
        (500, ProviderErrorCategory.UPSTREAM),
        (503, ProviderErrorCategory.UPSTREAM),
    ],
)
def test_provider_http_errors_are_sanitized(status_code, category, caplog) -> None:
    async def scenario() -> None:
        async def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(status_code, text=f"provider body contains {SECRET}")

        client = _client(handler)
        try:
            with pytest.raises(ProviderError) as raised:
                await client.stat()
        finally:
            await client.aclose()

        assert raised.value.category is category
        assert SECRET not in str(raised.value)
        assert SECRET not in caplog.text
        assert "provider body" not in str(raised.value)

    with caplog.at_level(logging.DEBUG):
        asyncio.run(scenario())


@pytest.mark.parametrize(
    ("raised_error", "category"),
    [
        (httpx.ReadTimeout("contains secret " + SECRET), ProviderErrorCategory.TIMEOUT),
        (httpx.ConnectError("contains secret " + SECRET), ProviderErrorCategory.CONNECTION),
    ],
)
def test_transport_errors_are_sanitized(raised_error, category) -> None:
    async def scenario() -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            raised_error.request = request
            raise raised_error

        client = _client(handler)
        try:
            with pytest.raises(ProviderError) as raised:
                await client.stat()
        finally:
            await client.aclose()

        assert raised.value.category is category
        assert SECRET not in str(raised.value)

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("response", "category"),
    [
        (httpx.Response(200, text="not-json"), ProviderErrorCategory.MALFORMED_RESPONSE),
        (httpx.Response(200, json={"meta": {"success": True}}), ProviderErrorCategory.MALFORMED_RESPONSE),
        (
            httpx.Response(200, json=_stat_payload(success=False)),
            ProviderErrorCategory.UNSUCCESSFUL_RESPONSE,
        ),
    ],
)
def test_malformed_and_unsuccessful_responses_fail_closed(response, category) -> None:
    async def scenario() -> None:
        async def handler(_request: httpx.Request) -> httpx.Response:
            return response

        client = _client(handler)
        try:
            with pytest.raises(ProviderError) as raised:
                await client.stat()
        finally:
            await client.aclose()
        assert raised.value.category is category

    asyncio.run(scenario())


def test_radius_rejects_more_than_45_nm_before_http() -> None:
    with pytest.raises(ValueError, match="45"):
        RadiusQuery(latitude=22.5, longitude=120.25, radius_nm=45.001)


def test_area_provider_limits_concurrency_to_two() -> None:
    async def scenario() -> None:
        active = 0
        maximum = 0

        async def handler(_request: httpx.Request) -> httpx.Response:
            nonlocal active, maximum
            active += 1
            maximum = max(maximum, active)
            await asyncio.sleep(0.01)
            active -= 1
            return httpx.Response(200, json=_radius_payload())

        client = _client(handler)
        provider = DatalasticAreaScanProvider(client)
        queries = tuple(
            RadiusQuery(latitude=22.5, longitude=120.0 + index / 100, radius_nm=2)
            for index in range(5)
        )
        try:
            result = await provider.scan(queries)
        finally:
            await client.aclose()

        assert len(result) == 5
        assert maximum == 2

    asyncio.run(scenario())


def test_scan_shares_one_short_429_retry_across_all_circles() -> None:
    async def scenario() -> None:
        attempts: dict[str, int] = {}
        sleeps: list[float] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            lon = request.url.params["lon"]
            attempts[lon] = attempts.get(lon, 0) + 1
            if attempts[lon] == 1:
                return httpx.Response(429, headers={"Retry-After": "1"})
            return httpx.Response(200, json=_radius_payload())

        async def fake_sleep(seconds: float) -> None:
            sleeps.append(seconds)

        client = _client(handler, sleep=fake_sleep)
        provider = DatalasticAreaScanProvider(client)
        queries = (
            RadiusQuery(latitude=22.5, longitude=120.1, radius_nm=2),
            RadiusQuery(latitude=22.5, longitude=120.2, radius_nm=2),
        )
        try:
            with pytest.raises(ProviderError) as raised:
                await provider.scan(queries)
        finally:
            await client.aclose()

        assert raised.value.category is ProviderErrorCategory.RATE_LIMITED
        assert sum(attempts.values()) == 3
        assert sleeps == [1.0]

    asyncio.run(scenario())


def test_long_retry_after_returns_immediately_without_sleeping() -> None:
    async def scenario() -> None:
        sleeps: list[float] = []

        async def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(429, headers={"Retry-After": "30"})

        async def fake_sleep(seconds: float) -> None:
            sleeps.append(seconds)

        client = _client(handler, sleep=fake_sleep)
        provider = DatalasticAreaScanProvider(client)
        try:
            with pytest.raises(ProviderError) as raised:
                await provider.scan((RadiusQuery(22.5, 120.2, 2),))
        finally:
            await client.aclose()

        assert raised.value.category is ProviderErrorCategory.RATE_LIMITED
        assert raised.value.retry_after_seconds is None
        assert sleeps == []

    asyncio.run(scenario())


@pytest.mark.parametrize("retry_after", ["-1", "999999999999999999999999"])
def test_unsafe_retry_after_is_not_reflected_or_slept(retry_after: str) -> None:
    async def scenario() -> None:
        sleeps: list[float] = []

        async def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(429, headers={"Retry-After": retry_after})

        async def fake_sleep(seconds: float) -> None:
            sleeps.append(seconds)

        client = _client(handler, sleep=fake_sleep)
        provider = DatalasticAreaScanProvider(client)
        try:
            with pytest.raises(ProviderError) as raised:
                await provider.scan((RadiusQuery(22.5, 120.2, 2),))
        finally:
            await client.aclose()

        assert raised.value.category is ProviderErrorCategory.RATE_LIMITED
        assert raised.value.retry_after_seconds is None
        assert sleeps == []

    asyncio.run(scenario())


def test_provider_concurrency_limit_is_shared_across_simultaneous_scans() -> None:
    async def scenario() -> None:
        active = 0
        maximum = 0

        async def handler(_request: httpx.Request) -> httpx.Response:
            nonlocal active, maximum
            active += 1
            maximum = max(maximum, active)
            await asyncio.sleep(0.02)
            active -= 1
            return httpx.Response(200, json=_radius_payload())

        client = _client(handler)
        provider = DatalasticAreaScanProvider(client)
        first = tuple(RadiusQuery(22.5, 120.0 + i / 100, 2) for i in range(3))
        second = tuple(RadiusQuery(23.5, 121.0 + i / 100, 2) for i in range(3))
        try:
            await asyncio.gather(provider.scan(first), provider.scan(second))
        finally:
            await client.aclose()

        assert maximum == 2

    asyncio.run(scenario())


def test_provider_concurrency_limit_also_covers_status_probe() -> None:
    async def scenario() -> None:
        active = 0
        maximum = 0

        async def handler(request: httpx.Request) -> httpx.Response:
            nonlocal active, maximum
            active += 1
            maximum = max(maximum, active)
            await asyncio.sleep(0.02)
            active -= 1
            if request.url.path.endswith("/stat"):
                return httpx.Response(200, json=_stat_payload())
            return httpx.Response(200, json=_radius_payload())

        client = _client(handler)
        provider = DatalasticAreaScanProvider(client)
        queries = tuple(
            RadiusQuery(22.5, 120.0 + index / 100, 2) for index in range(4)
        )
        try:
            await asyncio.gather(client.stat(), provider.scan(queries))
        finally:
            await client.aclose()

        assert maximum == 2

    asyncio.run(scenario())


def test_terminal_failure_stops_queued_circle_requests() -> None:
    async def scenario() -> None:
        requested: list[str] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            longitude = request.url.params["lon"]
            requested.append(longitude)
            if longitude == "120.0":
                return httpx.Response(401)
            await asyncio.sleep(0.03)
            return httpx.Response(200, json=_radius_payload())

        client = _client(handler)
        provider = DatalasticAreaScanProvider(client)
        queries = tuple(RadiusQuery(22.5, 120.0 + i / 10, 2) for i in range(5))
        try:
            with pytest.raises(ProviderError) as raised:
                await provider.scan(queries)
        finally:
            await client.aclose()

        assert raised.value.category is ProviderErrorCategory.AUTHENTICATION
        assert len(requested) <= 2

    asyncio.run(scenario())


def test_status_cache_exposes_only_sanitized_state() -> None:
    cache = DatalasticStatusCache(configured=True)
    initial = cache.snapshot()
    assert initial.reachable is None
    assert initial.key_status == "unknown"

    cache.record_failure(ProviderErrorCategory.AUTHENTICATION)
    failed = cache.snapshot().to_public_dict()
    assert failed["reachable"] is False
    assert failed["last_error_category"] == "authentication"
    assert "user_id" not in failed
    assert SECRET not in repr(failed)
