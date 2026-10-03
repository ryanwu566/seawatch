"""Maritime context API router (read-only, additive).

Exposes geographic context facts for a vessel position. Stateless and pure: it
takes the position the caller already holds (from the live feed) and returns
provenance-labeled geometry. It touches no ``/live/*``, ``/resilience/*``,
``/edge/*``, or ``/logistics/*`` route and shares no mutable state with Phase 8
or Phase 9. It performs no outbound network call, no DB access, and no
classification.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from ..context.gis import resolve_geographic_context

router = APIRouter(prefix="/context", tags=["context"])


@router.get(
    "/geographic",
    summary="Geographic context facts for a vessel position (read-only)",
)
def geographic_context(
    lon: float = Query(..., description="Longitude (WGS84, degrees)"),
    lat: float = Query(..., description="Latitude (WGS84, degrees)"),
) -> dict:
    """Return provenance-labeled geographic context for a position.

    Answers "what is around this position?": distance to coast, nearest civilian
    port + distance, and which named maritime area(s) contain the position. Port
    and area *definitions* are ``official`` reference data; distances and
    containment are ``derived``; a position outside reference coverage yields an
    ``unknown`` result. It never derives a violation, restricted-area, or
    legality judgement.
    """

    if not (-180.0 <= lon <= 180.0 and -90.0 <= lat <= 90.0):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="lon must be in [-180,180] and lat in [-90,90]",
        )
    return resolve_geographic_context(lon, lat).to_dict()
