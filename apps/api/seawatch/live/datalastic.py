"""Request-driven Datalastic Live AIS client with privacy-safe failures."""

from __future__ import annotations

import asyncio
import math
import os
import re
import threading
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from typing import Any

import httpx


DEFAULT_DATALASTIC_BASE_URL = "https://api.datalastic.com/api/v0/"
MAX_PROVIDER_RADIUS_NM = 50.0
MAX_SCAN_RADIUS_NM = 45.0
MAX_CONCURRENT_REQUESTS = 2
MAX_INTERACTIVE_RETRY_AFTER_SECONDS = 5.0


class ProviderErrorCategory(str, Enum):
    NOT_CONFIGURED = "not_configured"
    TIMEOUT = "timeout"
    CONNECTION = "connection"
    AUTHENTICATION = "authentication"
    RATE_LIMITED = "rate_limited"
    QUOTA_EXHAUSTED = "quota_exhausted"
    UPSTREAM = "upstream"
    MALFORMED_RESPONSE = "malformed_response"
    UNSUCCESSFUL_RESPONSE = "unsuccessful_response"


class ProviderError(RuntimeError):
    """Sanitized upstream failure safe for logs and API responses."""

    def __init__(
        self,
        category: ProviderErrorCategory,
        *,
        retry_after_seconds: int | None = None,
    ) -> None:
        self.category = category
        self.retry_after_seconds = retry_after_seconds
        super().__init__(f"Datalastic provider unavailable ({category.value})")


@dataclass(frozen=True)
class DatalasticConfig:
    api_key: str | None = field(default=None, repr=False)
    base_url: str = DEFAULT_DATALASTIC_BASE_URL
    connect_timeout_seconds: float = 3.0
    read_timeout_seconds: float = 8.0

    def __post_init__(self) -> None:
        normalized_key = self.api_key.strip() if self.api_key else None
        normalized_url = self.base_url.strip().rstrip("/") + "/"
        object.__setattr__(self, "api_key", normalized_key or None)
        object.__setattr__(self, "base_url", normalized_url)

    @property
    def configured(self) -> bool:
        return self.api_key is not None

    @classmethod
    def from_env(
        cls, values: Mapping[str, str] | None = None
    ) -> "DatalasticConfig":
        env = os.environ if values is None else values
        return cls(
            api_key=env.get("DATALASTIC_API_KEY"),
            base_url=env.get("DATALASTIC_BASE_URL", DEFAULT_DATALASTIC_BASE_URL),
        )


@dataclass(frozen=True)
class RadiusQuery:
    latitude: float
    longitude: float
    radius_nm: float

    def __post_init__(self) -> None:
        if not -90 <= self.latitude <= 90:
            raise ValueError("latitude must be between -90 and 90")
        if not -180 <= self.longitude <= 180:
            raise ValueError("longitude must be between -180 and 180")
        if not 0 < self.radius_nm <= MAX_SCAN_RADIUS_NM:
            raise ValueError("radius must be greater than 0 and at most 45 NM")
        if self.radius_nm > MAX_PROVIDER_RADIUS_NM:
            raise ValueError("radius exceeds the 50 NM provider maximum")


@dataclass(frozen=True)
class DatalasticVessel:
    uuid: str | None
    name: str | None
    mmsi: int | None
    imo: int | None
    latitude: float
    longitude: float
    speed_knots: float | None
    course_deg: float | None
    heading_deg: float | None
    navigation_status: str | None
    vessel_type: str | None
    vessel_type_specific: str | None
    destination: str | None
    observed_at: datetime | None


@dataclass(frozen=True)
class DatalasticStatus:
    configured: bool
    reachable: bool | None
    key_status: str
    addons: bool | None
    requests_remaining: int | None
    rate_limit_remaining: int | None
    last_success_at: datetime | None
    last_error_category: ProviderErrorCategory | None

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "provider": "datalastic",
            "configured": self.configured,
            "reachable": self.reachable,
            "key_status": self.key_status,
            "addons": self.addons,
            "requests_remaining": self.requests_remaining,
            "rate_limit_remaining": self.rate_limit_remaining,
            "last_success_at": (
                self.last_success_at.isoformat() if self.last_success_at else None
            ),
            "last_error_category": (
                self.last_error_category.value if self.last_error_category else None
            ),
        }


class DatalasticStatusCache:
    """Thread-safe cached status; reads never contact the provider."""

    def __init__(self, *, configured: bool) -> None:
        self._lock = threading.Lock()
        self._status = DatalasticStatus(
            configured=configured,
            reachable=None if configured else False,
            key_status="unknown",
            addons=None,
            requests_remaining=None,
            rate_limit_remaining=None,
            last_success_at=None,
            last_error_category=None,
        )

    def snapshot(self) -> DatalasticStatus:
        with self._lock:
            return self._status

    def record_success(self, status: DatalasticStatus) -> None:
        with self._lock:
            self._status = status

    def record_failure(self, category: ProviderErrorCategory) -> None:
        with self._lock:
            self._status = replace(
                self._status,
                reachable=False,
                key_status=(
                    "invalid"
                    if category is ProviderErrorCategory.AUTHENTICATION
                    else self._status.key_status
                ),
                last_error_category=category,
            )

    def record_reachable(self) -> None:
        with self._lock:
            self._status = replace(
                self._status,
                reachable=True,
                last_success_at=datetime.now(timezone.utc),
                last_error_category=None,
            )


class ScanRetryBudget:
    """One retry token shared by every circle in one manual scan."""

    def __init__(self, *, max_wait_seconds: float = MAX_INTERACTIVE_RETRY_AFTER_SECONDS) -> None:
        self._lock = asyncio.Lock()
        self._used = False
        self._max_wait_seconds = max_wait_seconds

    async def claim(self, retry_after_seconds: int | None) -> float | None:
        if retry_after_seconds is None or retry_after_seconds > self._max_wait_seconds:
            return None
        async with self._lock:
            if self._used:
                return None
            self._used = True
            return float(retry_after_seconds)


SleepCallable = Callable[[float], Awaitable[None]]


class DatalasticClient:
    """Small async client for the two Datalastic endpoints SeaWatch uses."""

    def __init__(
        self,
        config: DatalasticConfig,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: SleepCallable = asyncio.sleep,
    ) -> None:
        self.config = config
        self._sleep = sleep
        # One runtime-owned client is shared by status and scan traffic, so the
        # ceiling applies process-wide rather than only within a single scan.
        self._request_semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
        timeout = httpx.Timeout(
            connect=config.connect_timeout_seconds,
            read=config.read_timeout_seconds,
            write=config.read_timeout_seconds,
            pool=config.connect_timeout_seconds,
        )
        headers = {"Accept": "application/json"}
        if config.api_key:
            headers["x-api-key"] = config.api_key
        self._http = httpx.AsyncClient(
            base_url=config.base_url,
            headers=headers,
            timeout=timeout,
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    @asynccontextmanager
    async def request_slot(self) -> AsyncIterator[None]:
        """Reserve one of the process-wide Datalastic request slots."""

        async with self._request_semaphore:
            yield

    async def stat(self) -> DatalasticStatus:
        response, payload = await self._request_json("stat")
        data = _require_mapping(payload.get("data"))
        key_status_raw = data.get("key_status")
        if not isinstance(key_status_raw, str):
            raise ProviderError(ProviderErrorCategory.MALFORMED_RESPONSE)
        key_status_normalized = key_status_raw.strip().lower()
        key_status = (
            key_status_normalized
            if key_status_normalized in {"valid", "invalid"}
            else "unknown"
        )
        addons = data.get("addons")
        if addons is not None and not isinstance(addons, bool):
            raise ProviderError(ProviderErrorCategory.MALFORMED_RESPONSE)
        return DatalasticStatus(
            configured=True,
            reachable=True,
            key_status=key_status,
            addons=addons,
            requests_remaining=_optional_int(data.get("requests_remaining")),
            rate_limit_remaining=_header_int(
                response.headers.get("X-Ratelimit-Remaining")
            ),
            last_success_at=datetime.now(timezone.utc),
            last_error_category=None,
        )

    async def vessels_in_radius(
        self,
        query: RadiusQuery,
        retry_budget: ScanRetryBudget | None = None,
        *,
        request_slot_reserved: bool = False,
    ) -> tuple[DatalasticVessel, ...]:
        params = {
            "lat": str(query.latitude),
            "lon": str(query.longitude),
            "radius": str(query.radius_nm),
        }
        response, payload = await self._request_json(
            "vessel_inradius",
            params=params,
            retry_budget=retry_budget,
            request_slot_reserved=request_slot_reserved,
        )
        del response
        data = _require_mapping(payload.get("data"))
        raw_vessels = data.get("vessels")
        if not isinstance(raw_vessels, list):
            raise ProviderError(ProviderErrorCategory.MALFORMED_RESPONSE)
        try:
            return tuple(_parse_vessel(item) for item in raw_vessels)
        except ProviderError:
            raise
        except (TypeError, ValueError, OverflowError):
            raise ProviderError(ProviderErrorCategory.MALFORMED_RESPONSE) from None

    async def _request_json(
        self,
        path: str,
        *,
        params: Mapping[str, str] | None = None,
        retry_budget: ScanRetryBudget | None = None,
        request_slot_reserved: bool = False,
    ) -> tuple[httpx.Response, dict[str, Any]]:
        if not self.config.configured:
            raise ProviderError(ProviderErrorCategory.NOT_CONFIGURED)
        while True:
            try:
                if request_slot_reserved:
                    response = await self._http.get(path, params=params)
                else:
                    async with self.request_slot():
                        response = await self._http.get(path, params=params)
            except httpx.TimeoutException:
                raise ProviderError(ProviderErrorCategory.TIMEOUT) from None
            except httpx.RequestError:
                raise ProviderError(ProviderErrorCategory.CONNECTION) from None

            if response.status_code in {401, 403}:
                raise ProviderError(ProviderErrorCategory.AUTHENTICATION)
            if response.status_code == 402:
                raise ProviderError(ProviderErrorCategory.QUOTA_EXHAUSTED)
            if response.status_code == 429:
                retry_after = _retry_after_seconds(response.headers.get("Retry-After"))
                delay = (
                    await retry_budget.claim(retry_after)
                    if retry_budget is not None
                    else None
                )
                if delay is None:
                    raise ProviderError(
                        ProviderErrorCategory.RATE_LIMITED,
                        retry_after_seconds=retry_after,
                    )
                await self._sleep(delay)
                continue
            if response.status_code >= 500:
                raise ProviderError(ProviderErrorCategory.UPSTREAM)
            if response.status_code >= 400:
                raise ProviderError(ProviderErrorCategory.UPSTREAM)

            try:
                payload = response.json()
            except (ValueError, TypeError):
                raise ProviderError(ProviderErrorCategory.MALFORMED_RESPONSE) from None
            if not isinstance(payload, dict):
                raise ProviderError(ProviderErrorCategory.MALFORMED_RESPONSE)
            meta = _require_mapping(payload.get("meta"))
            if meta.get("success") is not True:
                raise ProviderError(ProviderErrorCategory.UNSUCCESSFUL_RESPONSE)
            return response, payload


class DatalasticAreaScanProvider:
    """Execute a bounded set of circle queries under one shared budget."""

    def __init__(self, client: DatalasticClient) -> None:
        self._client = client

    async def scan(
        self, queries: Sequence[RadiusQuery]
    ) -> tuple[DatalasticVessel, ...]:
        if not queries:
            return ()
        retry_budget = ScanRetryBudget()
        stopped = asyncio.Event()

        async def one(query: RadiusQuery) -> tuple[DatalasticVessel, ...]:
            if stopped.is_set():
                return ()
            async with self._client.request_slot():
                if stopped.is_set():
                    return ()
                try:
                    return await self._client.vessels_in_radius(
                        query,
                        retry_budget,
                        request_slot_reserved=True,
                    )
                except ProviderError:
                    stopped.set()
                    raise
                except asyncio.CancelledError:
                    raise
                except Exception:
                    stopped.set()
                    raise ProviderError(ProviderErrorCategory.UPSTREAM) from None

        tasks = [asyncio.create_task(one(query)) for query in queries]
        try:
            done, pending = await asyncio.wait(
                tasks, return_when=asyncio.FIRST_EXCEPTION
            )
            failure: ProviderError | None = None
            for task in tasks:
                if task not in done or task.cancelled():
                    continue
                exception = task.exception()
                if isinstance(exception, ProviderError):
                    failure = exception
                    break
            if failure is not None:
                stopped.set()
                for task in pending:
                    task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)
                raise failure
            results = await asyncio.gather(*tasks)
            return tuple(vessel for result in results for vessel in result)
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()


def _require_mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ProviderError(ProviderErrorCategory.MALFORMED_RESPONSE)
    return value


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ProviderError(ProviderErrorCategory.MALFORMED_RESPONSE)
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if re.fullmatch(r"[0-9]+", stripped):
            return int(stripped)
    raise ProviderError(ProviderErrorCategory.MALFORMED_RESPONSE)


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ProviderError(ProviderErrorCategory.MALFORMED_RESPONSE)
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ProviderError(ProviderErrorCategory.MALFORMED_RESPONSE)
    return parsed


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ProviderError(ProviderErrorCategory.MALFORMED_RESPONSE)
    stripped = value.strip()
    return stripped or None


def _parse_datetime(value: Any, epoch: Any) -> datetime | None:
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    if epoch is not None:
        return datetime.fromtimestamp(float(epoch), tz=timezone.utc)
    if value is None:
        return None
    raise ProviderError(ProviderErrorCategory.MALFORMED_RESPONSE)


def _parse_vessel(value: Any) -> DatalasticVessel:
    data = _require_mapping(value)
    latitude = float(data["lat"])
    longitude = float(data["lon"])
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise ProviderError(ProviderErrorCategory.MALFORMED_RESPONSE)
    return DatalasticVessel(
        uuid=_optional_string(data.get("uuid")),
        name=_optional_string(data.get("name")),
        mmsi=_optional_int(data.get("mmsi")),
        imo=_optional_int(data.get("imo")),
        latitude=latitude,
        longitude=longitude,
        speed_knots=_optional_float(data.get("speed")),
        course_deg=_optional_float(data.get("course")),
        heading_deg=_optional_float(data.get("heading")),
        navigation_status=_optional_string(data.get("navigation_status")),
        vessel_type=_optional_string(data.get("type")),
        vessel_type_specific=_optional_string(data.get("type_specific")),
        destination=_optional_string(data.get("destination")),
        observed_at=_parse_datetime(
            data.get("last_position_UTC"), data.get("last_position_epoch")
        ),
    )


def _header_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _retry_after_seconds(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        parsed = int(value.strip())
    except ValueError:
        return None
    if not 0 <= parsed <= int(MAX_INTERACTIVE_RETRY_AFTER_SECONDS):
        return None
    return parsed
