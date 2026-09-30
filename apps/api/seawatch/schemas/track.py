"""Track metadata response schemas.

Trajectory metadata is exposed as behavioral observations only. Vessel identity
fields (MMSI, vessel name, IMO, call sign) are never present in Phase 3B outputs
and are never surfaced here.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class TrackMetadata(BaseModel):
    """Privacy-safe trajectory metadata for a single ranked review window."""

    track_id: str = Field(..., description="Date-scoped surrogate track identifier.")
    date: str = Field(..., description="Source date (ISO 8601) the observation belongs to.")
    duration: float = Field(
        ...,
        description="Observed trajectory-window duration in seconds.",
        ge=0.0,
    )
    observation_count: int = Field(
        ...,
        description="Number of AIS observations in the window.",
        ge=0,
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "track_id": "2024-01-03__t-000042",
                "date": "2024-01-03",
                "duration": 3540.0,
                "observation_count": 118,
            }
        }
    }


class TrackListResponse(BaseModel):
    """Envelope for the available trajectory metadata collection."""

    count: int = Field(..., description="Number of track metadata records returned.", ge=0)
    tracks: list[TrackMetadata] = Field(default_factory=list)
