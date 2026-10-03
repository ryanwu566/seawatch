"""Normalized, privacy-conscious live AIS observation schema.

This is the single internal representation every live provider is normalized
into. It deliberately keeps the data integrity fields SeaWatch promises to the
operator: when an observation was reported (``observed_at``), when the server
received it (``received_at``), which upstream feed produced it (``source``), and
whether the provider *interpolated* the position (``synthesized``) rather than
reporting a measured AIS fix.

Vessel identity (MMSI/IMO) may be carried internally for deduplication and for
building per-vessel trajectories, but the public API layer never has to expose
it. ``provider_id`` is the stable key used by the store and the API.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def utcnow() -> datetime:
    """Timezone-aware current UTC time (single definition for testability)."""

    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class LiveVesselObservation:
    """One normalized real AIS observation for a single vessel.

    All coordinates are WGS84 (EPSG:4326). Movement fields are optional because
    real AIS messages frequently omit them. Nothing here is fabricated: a field
    is ``None`` when the upstream frame did not provide it.
    """

    provider_id: str
    """Stable per-vessel key within a provider (e.g. the MMSI as a string)."""

    latitude: float
    longitude: float

    observed_at: datetime
    """When the position was reported upstream (AIS/provider timestamp, UTC)."""

    received_at: datetime
    """When this server ingested the frame (UTC). Never upstream-provided."""

    source: str
    """Provider / upstream feed label, e.g. ``open_waters`` or ``aishub``."""

    sog_knots: float | None = None
    cog_deg: float | None = None
    heading_deg: float | None = None
    nav_status: int | None = None
    vessel_type: int | None = None
    """Numeric AIS ship-and-cargo type code (ITU-R M.1371), when known."""

    name: str | None = None
    destination: str | None = None

    synthesized: bool = False
    """True when the provider interpolated the position rather than reporting a
    measured AIS fix. Surfaced so the UI never claims interpolation is measured."""

    # Carried internally for dedup only; not required by the public UI.
    mmsi: int | None = None

    # Internal only (never in the public bag): the provider's free-text vessel class, e.g. a registry 'Research vessel'. Detection uses it as a declaration.
    vessel_subtype: str | None = None

    def age_seconds(self, *, now: datetime | None = None) -> float:
        """Seconds since the position was reported upstream."""

        reference = now or utcnow()
        return max(0.0, (reference - self.observed_at).total_seconds())

    def to_public_properties(self, *, public_id: str) -> dict[str, Any]:
        """Privacy-conscious property bag for the public API.

        Includes the data integrity fields and useful civilian attributes.
        MMSI/IMO are intentionally omitted; ``provider_id`` is opaque to clients.
        """

        return {
            "provider_id": public_id,
            "sog_knots": self.sog_knots,
            "cog_deg": self.cog_deg,
            "heading_deg": self.heading_deg,
            "nav_status": self.nav_status,
            "vessel_type": self.vessel_type,
            "name": self.name,
            "destination": self.destination,
            "observed_at": self.observed_at.isoformat(),
            "source": self.source,
            "synthesized": self.synthesized,
        }


@dataclass
class TrajectoryPoint:
    """A single retained position in a vessel's rolling trajectory."""

    latitude: float
    longitude: float
    observed_at: datetime
    synthesized: bool = False


@dataclass
class VesselState:
    """The latest observation plus a bounded rolling trajectory for a vessel."""

    provider_id: str
    latest: LiveVesselObservation
    trajectory: list[TrajectoryPoint] = field(default_factory=list)
