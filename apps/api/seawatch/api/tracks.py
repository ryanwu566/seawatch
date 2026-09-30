"""Tracks endpoint router."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from ..schemas.track import TrackListResponse
from ..services import track_service
from ..services.artifacts import MissingArtifactError

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
