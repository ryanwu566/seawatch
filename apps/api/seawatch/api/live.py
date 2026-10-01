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

from ..live import BoundingBox, get_consumer, get_store
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

    return get_consumer().health_snapshot()


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

    store = get_store()
    bbox = _parse_bbox(min_lat, min_lon, max_lat, max_lon)
    now = utcnow()
    observations = store.snapshot(bbox=bbox)
    features = []
    for obs in observations:
        props = obs.to_public_properties()
        props["data_age_seconds"] = round(obs.age_seconds(now=now), 1)
        features.append(
            {
                "type": "Feature",
                "id": obs.provider_id,
                "geometry": {
                    "type": "Point",
                    "coordinates": [obs.longitude, obs.latitude],
                },
                "properties": props,
            }
        )
    last_message_at = store.last_message_at()
    return {
        "type": "FeatureCollection",
        "attribution": "Open Waters AIS (https://openwaters.io/ais/)",
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

    store = get_store()
    trajectory = store.get_trajectory(vessel_id)
    if trajectory is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"vessel not found: {vessel_id}",
        )
    coordinates = [[p.longitude, p.latitude] for p in trajectory]
    return {
        "type": "Feature",
        "id": vessel_id,
        "geometry": {"type": "LineString", "coordinates": coordinates},
        "properties": {
            "provider_id": vessel_id,
            "point_count": len(coordinates),
            "observed_from": trajectory[0].observed_at.isoformat() if trajectory else None,
            "observed_to": trajectory[-1].observed_at.isoformat() if trajectory else None,
        },
    }
