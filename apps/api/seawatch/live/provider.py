"""Live AIS provider abstraction.

A provider knows how to connect to one upstream real-time AIS feed, how to build
its subscription for a Taiwan bounding box, and how to normalize an upstream
frame into a :class:`LiveVesselObservation`. The ingest consumer drives the
connection; providers stay thin and testable (frame parsing is pure).
"""

from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class BoundingBox:
    """A geographic bounding box in degrees (WGS84)."""

    min_lat: float
    min_lon: float
    max_lat: float
    max_lon: float

    def contains(self, lat: float | None, lon: float | None) -> bool:
        if lat is None or lon is None:
            return False
        return (
            self.min_lat <= lat <= self.max_lat
            and self.min_lon <= lon <= self.max_lon
        )

    def area_sq_degrees(self) -> float:
        return abs(self.max_lat - self.min_lat) * abs(self.max_lon - self.min_lon)


# Default Taiwan test/operating box validated in Phase 7A smoke tests.
TAIWAN_BBOX = BoundingBox(min_lat=21.5, min_lon=118.0, max_lat=26.5, max_lon=123.5)


class LiveAisProvider(abc.ABC):
    """Interface implemented by each real-time AIS source."""

    #: Stable provider identifier used in health/attribution (e.g. ``open_waters``).
    name: str

    @property
    @abc.abstractmethod
    def websocket_url(self) -> str:
        """The upstream WebSocket URL to connect to."""

    @abc.abstractmethod
    def requires_credentials(self) -> bool:
        """Whether a credential must be present before connecting."""

    @abc.abstractmethod
    def subscription_message(self, bbox: BoundingBox) -> dict[str, Any]:
        """Build the JSON subscription payload for the given bounding box."""

    @abc.abstractmethod
    def parse_frame(self, frame: Any) -> "ParsedFrame":
        """Normalize a decoded upstream frame.

        Pure function: no I/O. Returns a :class:`ParsedFrame` describing whether
        the frame was an acknowledgement, a position observation, or ignorable.
        """


@dataclass(frozen=True)
class ParsedFrame:
    """Result of normalizing one upstream frame."""

    kind: str  # "ack" | "position" | "other"
    observation: Any | None = None  # LiveVesselObservation when kind == "position"
    detail: dict[str, Any] | None = None
