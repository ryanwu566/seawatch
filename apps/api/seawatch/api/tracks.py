"""Tracks endpoint router."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from ..schemas.geometry import LineStringGeometry, TrackGeometryResponse
from ..schemas.track import TrackListResponse
from ..services import geometry_service, track_service
from ..services.artifacts import MissingArtifactError
from ..services.geometry_service import MissingArtifactError as MissingGeometryArtifactError

router = APIRouter(tags=["tracks"])


@router.get("/tracks", response_model=TrackListResponse, summary="List trajectory metadata")
def get_tracks() -> TrackListResponse:
    """Return available privacy-safe trajectory metadata.

    Never exposes vessel identity (MMSI, vessel name, IMO, call sign).
    """

    try:
        tracks = track_service.list_tracks()
    except MissingArtifactError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    return TrackListResponse(count=len(tracks), tracks=tracks)


@router.get(
    "/tracks/{track_id}/geometry",
    response_model=TrackGeometryResponse,
    summary="Get privacy-safe track geometry",
)
def get_track_geometry(track_id: str) -> TrackGeometryResponse:
    """Return the track trajectory as a GeoJSON LineString.

    Geometry is read from existing Phase 1 processed observations (coordinates
    only; no vessel identity). Returns 404 when the track has no available
    geometry (unknown track or fewer than two valid coordinates).
    """

    try:
        coordinates = geometry_service.get_track_line_coordinates(track_id)
    except MissingGeometryArtifactError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    if coordinates is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"track geometry unavailable: {track_id}",
        )
    return TrackGeometryResponse(
        track_id=track_id,
        geometry=LineStringGeometry(coordinates=coordinates),
    )
