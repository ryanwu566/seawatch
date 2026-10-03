"""Live real-time AIS endpoints.

Privacy-conscious, read-only access to the in-memory live vessel store. These
endpoints perform NO upstream network call: they read the shared store that the
single background ingest consumer feeds, so ``GET /live/vessels`` is fast.

Data integrity is preserved on every vessel: ``observed_at``, ``source``, and a
server-computed ``data_age_seconds`` so the frontend can distinguish a fresh
LIVE AIS fix from a cached/stale one. Nothing is synthesized server-side.
"""

from __future__ import annotations

import ipaddress
import re
import time
from typing import Literal

from fastapi import APIRouter, Cookie, Header, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field, ValidationError

from ..live import BoundingBox, get_live_runtime, get_resilience_status
from ..live.area_scan import AreaScanRequest, ScanValidationError, plan_scan_geometry
from ..live.area_scan_access import (
    AREA_SCAN_CAPABILITY_COOKIE,
    DEFAULT_CAPABILITY_TTL_SECONDS,
    AreaScanAdmissionError,
    mint_area_scan_capability,
    verify_area_scan_capability,
    verify_operator_credential,
)
from ..live.datalastic import (
    ProviderError,
    ProviderErrorCategory,
    refresh_datalastic_status,
)
from ..live.resilience import OperatingMode
from ..live.schema import utcnow

router = APIRouter(prefix="/live", tags=["live"])
_PUBLIC_VESSEL_ID = re.compile(r"^v_[A-Za-z0-9_-]{16,64}$")
_MAX_OPERATOR_SESSION_BODY_BYTES = 8_192
_AREA_SCAN_CSRF_HEADER = "x-seawatch-area-scan"
_AREA_SCAN_AUTOAUTH_HOSTS = {"localhost", "127.0.0.1"}


class AreaScanSessionRequest(BaseModel):
    operator_credential: str | None = Field(
        default=None,
        min_length=1,
        max_length=4_096,
    )


@router.post("/area-scan/session", summary="Create a short-lived Area Scan session")
async def create_area_scan_session(
    request: Request,
    response: Response,
) -> dict:
    """Authenticate an operator and issue an HttpOnly capability cookie."""

    runtime = get_live_runtime()
    access = runtime.area_scan_access
    if not access.configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Area Scan access is not configured",
        )
    _require_json_content_type(request)
    body = await _read_bounded_body(
        request,
        max_bytes=_MAX_OPERATOR_SESSION_BODY_BYTES,
        too_large_detail="Area Scan session request body is too large",
    )
    try:
        payload = AreaScanSessionRequest.model_validate_json(body)
    except (ValidationError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid Area Scan session request",
        ) from None
    loopback_request = _is_loopback_request(request)
    loopback_autoauth = access.autoauth_loopback and loopback_request
    if not loopback_autoauth:
        if not access.operator_configured:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Area Scan access is not configured",
            )
        if payload.operator_credential is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Area Scan operator authentication required",
            )
        if not verify_operator_credential(payload.operator_credential, access):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Area Scan operator authentication failed",
            )
    capability = mint_area_scan_capability(
        access,
        ttl_seconds=DEFAULT_CAPABILITY_TTL_SECONDS,
    )
    response.set_cookie(
        key=AREA_SCAN_CAPABILITY_COOKIE,
        value=capability,
        max_age=DEFAULT_CAPABILITY_TTL_SECONDS,
        httponly=True,
        secure=(access.secure_cookie and not loopback_autoauth) or not loopback_request,
        samesite="strict",
        path="/live/area-scan",
    )
    response.headers["Cache-Control"] = "no-store"
    return {
        "authenticated": True,
        "expires_in_seconds": DEFAULT_CAPABILITY_TTL_SECONDS,
    }


@router.post("/area-scan/plan", summary="Plan an Area Scan without provider requests")
async def plan_live_area_scan(
    request: Request,
    authorization: str | None = Header(default=None),
    capability_cookie: str | None = Cookie(
        default=None,
        alias=AREA_SCAN_CAPABILITY_COOKIE,
    ),
) -> dict:
    """Validate geometry and calculate its local provider-query plan."""

    runtime = get_live_runtime()
    _authorize_area_scan_request(
        request,
        runtime.area_scan_access,
        authorization,
        capability_cookie,
    )
    _require_json_content_type(request)
    body = await _read_bounded_body(
        request,
        max_bytes=runtime.area_scan_access.max_body_bytes,
        too_large_detail="Area Scan request body is too large",
    )
    try:
        scan_request = AreaScanRequest.model_validate_json(body)
        plan = plan_scan_geometry(scan_request)
    except (ValidationError, ValueError, ScanValidationError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid Area Scan geometry",
        ) from None
    return plan.to_public_dict()


@router.post(
    "/area-scan/provider-status/refresh",
    summary="Refresh Datalastic provider readiness",
)
async def refresh_area_scan_provider_status(
    request: Request,
    authorization: str | None = Header(default=None),
    capability_cookie: str | None = Cookie(
        default=None,
        alias=AREA_SCAN_CAPABILITY_COOKIE,
    ),
) -> dict:
    """Run one authenticated, rate-limited, non-billable status probe."""

    runtime = get_live_runtime()
    _authorize_area_scan_request(
        request,
        runtime.area_scan_access,
        authorization,
        capability_cookie,
    )
    try:
        runtime.area_scan_admission.authorize(provider_requests=1)
    except AreaScanAdmissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Provider status refresh limit reached",
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from None
    provider_status = await refresh_datalastic_status(
        runtime.datalastic_client,
        runtime.datalastic_status,
    )
    return provider_status.to_public_dict()


@router.post("/area-scan", summary="Explicit Datalastic polygon area scan")
async def live_area_scan(
    request: Request,
    authorization: str | None = Header(default=None),
    capability_cookie: str | None = Cookie(
        default=None,
        alias=AREA_SCAN_CAPABILITY_COOKIE,
    ),
) -> dict:
    """Scan one validated polygon only after an explicit client action."""

    runtime = get_live_runtime()
    _authorize_area_scan_request(
        request,
        runtime.area_scan_access,
        authorization,
        capability_cookie,
    )
    _require_json_content_type(request)
    body = await _read_bounded_body(
        request,
        max_bytes=runtime.area_scan_access.max_body_bytes,
        too_large_detail="Area Scan request body is too large",
    )
    try:
        scan_request = AreaScanRequest.model_validate_json(body)
    except (ValidationError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid Area Scan request",
        ) from None
    service = runtime.area_scan_service
    try:
        result = await service.scan(scan_request)
    except ScanValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from None
    except ProviderError as exc:
        if exc.category is ProviderErrorCategory.NOT_CONFIGURED:
            detail = "Datalastic Live AIS is not configured"
        elif exc.category is ProviderErrorCategory.QUOTA_EXHAUSTED:
            detail = "Datalastic quota exhausted"
        else:
            detail = "Datalastic Live AIS currently unavailable"
        headers = (
            {"Retry-After": str(exc.retry_after_seconds)}
            if exc.retry_after_seconds is not None
            and 0 <= exc.retry_after_seconds <= 5
            else None
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=detail,
            headers=headers,
        ) from None
    except AreaScanAdmissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Area Scan request budget exhausted",
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from None
    payload = result.to_public_dict()
    payload["detection"] = runtime.live_detection.snapshot().to_public_dict()
    return payload


def _authorize_area_scan_request(
    request: Request,
    access,
    authorization: str | None,
    capability_cookie: str | None,
) -> None:
    if not access.configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Area Scan access is not configured",
        )
    bearer_capability = None
    if authorization is not None and authorization.startswith("Bearer "):
        bearer_capability = authorization.removeprefix("Bearer ").strip()
    capability = bearer_capability or capability_cookie
    if not capability:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Area Scan authorization required",
        )
    if not verify_area_scan_capability(capability, access):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Area Scan authorization invalid or expired",
        )
    if (
        bearer_capability is None
        and capability_cookie is not None
        and request.headers.get(_AREA_SCAN_CSRF_HEADER) != "1"
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Area Scan request confirmation required",
        )


def _require_json_content_type(request: Request) -> None:
    """Reject browser-simple content types before parsing sensitive requests."""

    media_type = request.headers.get("content-type", "").split(";", 1)[0]
    if media_type.strip().lower() != "application/json":
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Area Scan requests require application/json",
        )


def _is_loopback_host(hostname: str | None) -> bool:
    if hostname is None:
        return False
    if hostname.casefold() == "localhost":
        return True
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False


def _is_loopback_request(request: Request) -> bool:
    """Require both the requested host and direct socket peer to be loopback."""

    client = request.client
    return (
        client is not None
        and request.url.hostname is not None
        and request.url.hostname.casefold() in _AREA_SCAN_AUTOAUTH_HOSTS
        and _is_loopback_host(client.host)
    )


async def _read_bounded_body(
    request: Request,
    *,
    max_bytes: int,
    too_large_detail: str,
) -> bytes:
    """Read a request body under a fixed cap without reflecting its contents."""

    body = bytearray()
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            declared_length = int(content_length)
        except ValueError:
            declared_length = -1
        if declared_length < 0 or declared_length > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=too_large_detail,
            )
    async for chunk in request.stream():
        if len(body) + len(chunk) > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=too_large_detail,
            )
        body.extend(chunk)
    return bytes(body)


def _parse_bbox(
    min_lat: float | None,
    min_lon: float | None,
    max_lat: float | None,
    max_lon: float | None,
) -> BoundingBox | None:
    provided = [min_lat, min_lon, max_lat, max_lon]
    if all(v is None for v in provided):
        return None
    if any(v is None for v in provided):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="bbox requires all of min_lat, min_lon, max_lat, max_lon",
        )
    return BoundingBox(min_lat=min_lat, min_lon=min_lon, max_lat=max_lat, max_lon=max_lon)  # type: ignore[arg-type]


@router.get("/health", summary="Live AIS ingest health")
def live_health() -> dict:
    """Return the live ingest health snapshot (connection, freshness, counts)."""

    runtime = get_live_runtime()
    resilience = get_resilience_status(runtime)
    result = runtime.cloud.consumer.health_snapshot()
    provider_status = runtime.datalastic_status.snapshot()
    if runtime.datalastic_config.configured:
        last_message_at = runtime.area_scan_service.last_message_at()
        last_message_monotonic = runtime.area_scan_service.last_message_monotonic()
        message_age = (
            max(0.0, time.monotonic() - last_message_monotonic)
            if last_message_monotonic is not None
            else None
        )
        vessel_count = runtime.area_scan_service.vessel_count()
        reachable = provider_status.reachable is True
        result.update(
            status=(
                "online"
                if reachable
                else "degraded"
                if vessel_count > 0
                else "offline"
            ),
            provider="datalastic",
            connected=reachable,
            subscribed=False,
            last_message_at=(
                last_message_at.isoformat() if last_message_at else None
            ),
            message_age_seconds=(
                round(message_age, 1) if message_age is not None else None
            ),
            vessel_count=vessel_count,
            reconnect_attempts=0,
            last_error=(
                provider_status.last_error_category.value
                if provider_status.last_error_category
                else None
            ),
        )
    if resilience.mode in {OperatingMode.EDGE_LIVE, OperatingMode.EDGE_REPLAY}:
        edge = runtime.edge.consumer.health.snapshot(runtime.edge.store, utcnow())
        result.update(
            status="online" if resilience.edge.fresh else "offline",
            provider="edge_replay"
            if resilience.mode is OperatingMode.EDGE_REPLAY
            else "edge_ais",
            connected=edge["receiver_active"],
            last_message_at=edge["last_valid_ais_at"],
            message_age_seconds=edge["message_age_seconds"],
            vessel_count=edge["local_vessel_count"],
            last_error=edge["last_error"],
        )
    result.update(
        mode=resilience.mode.value,
        coverage=resilience.coverage.value,
        simulated=resilience.simulated,
        cloud=_source_payload(resilience.cloud),
        edge=_source_payload(resilience.edge),
        provider_status=provider_status.to_public_dict(),
        live_ingest_enabled=runtime.config.live_ingest_enabled,
        area_scan_autoauth_loopback_enabled=(
            runtime.area_scan_access.autoauth_loopback
        ),
    )
    return result


def _source_payload(source) -> dict:
    return {
        "source": source.source,
        "fresh": source.fresh,
        "message_age_seconds": source.message_age_seconds,
        "vessel_count": source.vessel_count,
        "connected": source.connected,
        "input_kind": source.input_kind.value if source.input_kind else None,
    }


@router.get("/vessels", summary="Current real AIS vessel positions (GeoJSON)")
def live_vessels(
    min_lat: float | None = Query(default=None),
    min_lon: float | None = Query(default=None),
    max_lat: float | None = Query(default=None),
    max_lon: float | None = Query(default=None),
) -> dict:
    """Return current real AIS vessels as a GeoJSON FeatureCollection.

    Optional viewport bbox filtering via query params. Does not include per-vessel
    trajectory history (use ``/live/vessels/{id}/track``). Each feature carries
    the data integrity fields needed to label LIVE vs CACHED vs STALE client-side.
    """

    runtime = get_live_runtime()
    resilience = get_resilience_status(runtime)
    bbox = _parse_bbox(min_lat, min_lon, max_lat, max_lon)
    now = utcnow()
    observations = runtime.active_view.snapshot(resilience, bbox=bbox, now=now)
    features = []
    for public in observations:
        obs = public.observation
        props = obs.to_public_properties(public_id=public.public_id)
        props["data_age_seconds"] = round(obs.age_seconds(now=now), 1)
        props["observation_origin"] = public.origin.value
        props["display_state"] = public.display_state.value
        props["active_source"] = public.active_source
        props["coverage"] = public.coverage.value
        props["operating_mode"] = public.operating_mode.value
        features.append(
            {
                "type": "Feature",
                "id": public.public_id,
                "geometry": {
                    "type": "Point",
                    "coordinates": [obs.longitude, obs.latitude],
                },
                "properties": props,
            }
        )
    if resilience.mode is OperatingMode.CLOUD_LIVE:
        last_message_at = runtime.cloud.store.last_message_at()
    elif resilience.mode in {OperatingMode.EDGE_LIVE, OperatingMode.EDGE_REPLAY}:
        last_message_at = runtime.edge.store.last_message_at()
    else:
        last_message_at = None
    origins = {item.origin for item in observations}
    attribution_parts = []
    if any(origin.value == "cloud" for origin in origins):
        attribution_parts.append("Open Waters AIS (https://openwaters.io/ais/)")
    if any(origin.value in {"edge_rf", "edge_replay"} for origin in origins):
        attribution_parts.append("Local AIS receiver")
    return {
        "type": "FeatureCollection",
        "attribution": "; ".join(attribution_parts),
        "mode": resilience.mode.value,
        "coverage": resilience.coverage.value,
        "simulated": resilience.simulated,
        "server_timestamp": now.isoformat(),
        "data_timestamp": last_message_at.isoformat() if last_message_at else None,
        "vessel_count": len(features),
        "features": features,
    }


@router.get("/vessels/{vessel_id}/track", summary="Rolling real trajectory (GeoJSON LineString)")
def live_vessel_track(
    vessel_id: str,
    source: Literal["datalastic"] | None = Query(default=None),
) -> dict:
    """Return the vessel's rolling real trajectory as a GeoJSON LineString.

    Coordinates come only from retained real observations (default last 30 min).
    Returns 404 when the vessel is unknown. A single retained point yields an
    empty-coordinate LineString rather than a fabricated segment.
    """

    if _PUBLIC_VESSEL_ID.fullmatch(vessel_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vessel track not found",
        )
    runtime = get_live_runtime()
    track = None
    if source == "datalastic":
        track = runtime.area_scan_service.track(vessel_id)
    else:
        track = runtime.active_view.track(vessel_id)
        if track is None:
            track = runtime.area_scan_service.track(vessel_id)
    if track is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vessel track not found",
        )
    coordinates = [[p.longitude, p.latitude] for p in track.points]
    return {
        "type": "Feature",
        "id": vessel_id,
        "geometry": {"type": "LineString", "coordinates": coordinates},
        "properties": {
            "provider_id": vessel_id,
            "point_count": len(coordinates),
            "observed_from": track.points[0].observed_at.isoformat() if track.points else None,
            "observed_to": track.points[-1].observed_at.isoformat() if track.points else None,
            "source": track.source_name,
        },
    }
