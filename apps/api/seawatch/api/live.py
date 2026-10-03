"""Live real-time AIS endpoints.

Privacy-conscious, read-only access to the in-memory live vessel store. These
endpoints perform NO upstream network call: they read the shared store that the
single background ingest consumer feeds, so ``GET /live/vessels`` is fast.

Data integrity is preserved on every vessel: ``observed_at``, ``source``, and a
server-computed ``data_age_seconds`` so the frontend can distinguish a fresh
LIVE AIS fix from a cached/stale one. Nothing is synthesized server-side.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from ..live import BoundingBox, get_live_runtime, get_resilience_status
from ..live.resilience import OperatingMode
from ..live.schema import utcnow

router = APIRouter(prefix="/live", tags=["live"])


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
def live_vessel_track(vessel_id: str) -> dict:
    """Return the vessel's rolling real trajectory as a GeoJSON LineString.

    Coordinates come only from retained real observations (default last 30 min).
    Returns 404 when the vessel is unknown. A single retained point yields an
    empty-coordinate LineString rather than a fabricated segment.
    """

    track = get_live_runtime().active_view.track(vessel_id)
    if track is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"vessel not found: {vessel_id}",
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
