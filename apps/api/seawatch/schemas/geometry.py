"""Track geometry response schemas (privacy-safe GeoJSON).

Geometry is derived from Phase 1 processed observations and contains coordinates
only. No vessel identity is present.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class LineStringGeometry(BaseModel):
    """A GeoJSON LineString: an ordered list of [longitude, latitude] pairs."""

    type: Literal["LineString"] = "LineString"
    coordinates: list[list[float]] = Field(
        ...,
        description="Ordered [longitude, latitude] pairs (EPSG:4326).",
        min_length=2,
    )


class TrackGeometryResponse(BaseModel):
    """Privacy-safe geometry for a single track."""

    track_id: str = Field(..., description="Date-scoped surrogate track identifier.")
    geometry: LineStringGeometry

    model_config = {
        "json_schema_extra": {
            "example": {
                "track_id": "2024-01-03__t-000042",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [
                        [-122.4, 37.7],
                        [-122.3, 37.8],
                    ],
                },
            }
        }
    }
