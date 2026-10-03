"""Maritime context API router (read-only, additive).

Exposes geographic context facts for a vessel position. Stateless and pure: it
takes the position the caller already holds (from the live feed) and returns
provenance-labeled geometry. It touches no ``/live/*``, ``/resilience/*``,
``/edge/*``, or ``/logistics/*`` route and shares no mutable state with Phase 8
or Phase 9. It performs no outbound network call, no DB access, and no
classification.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import FileResponse

from ..context.gis import resolve_geographic_context

router = APIRouter(prefix="/context", tags=["context"])


class MaritimeReferenceAsset(str, Enum):
    """Public route names for the strictly allowlisted reference artifacts."""

    EEZ = "eez-reference.geojson"
    TERRITORIAL_SEA_12NM = "territorial-sea-12nm-reference.geojson"
    CONTIGUOUS_ZONE_24NM = "contiguous-zone-24nm-reference.geojson"


_MARITIME_REFERENCE_ROOT = (
    Path(__file__).resolve().parents[4]
    / "data"
    / "gis"
    / "taiwan_maritime_reference"
)
_MARITIME_REFERENCE_FILES = {
    MaritimeReferenceAsset.EEZ: _MARITIME_REFERENCE_ROOT / "eez_reference_areas.geojson",
    MaritimeReferenceAsset.TERRITORIAL_SEA_12NM: (
        _MARITIME_REFERENCE_ROOT / "territorial_sea_12nm_reference_polygon.geojson"
    ),
    MaritimeReferenceAsset.CONTIGUOUS_ZONE_24NM: (
        _MARITIME_REFERENCE_ROOT / "contiguous_zone_12_24nm_reference_band.geojson"
    ),
}


@router.get(
    "/maritime-reference/{asset}",
    summary="Canonical maritime reference geometry (read-only)",
    response_class=FileResponse,
)
def maritime_reference(asset: MaritimeReferenceAsset) -> FileResponse:
    """Serve one fixed canonical reference file without transforming geometry.

    The 12 NM polygon and 12–24 NM band are derived reference geometry. All
    three assets are reference-only and are not for navigation or legal
    adjudication. ``asset`` is an enum lookup; request text is never resolved as
    a filesystem path.
    """

    path = _MARITIME_REFERENCE_FILES[asset]
    if not path.is_file():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Maritime reference layer is unavailable",
        )
    return FileResponse(
        path,
        media_type="application/geo+json",
        headers={"Cache-Control": "public, max-age=3600"},
    )


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
