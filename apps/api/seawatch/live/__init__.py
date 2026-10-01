"""SeaWatch live real-time AIS foundation.

Provides the provider abstraction, the Open Waters provider (validated for live
Taiwan coverage in Phase 7A), an in-memory vessel store, and the background
ingest consumer. A single process-wide store and consumer are shared across all
FastAPI requests so the frontend never triggers an upstream call.
"""

from __future__ import annotations

from .ingest import AisIngestConsumer, IngestHealth
from .open_waters import OpenWatersProvider
from .provider import TAIWAN_BBOX, BoundingBox, LiveAisProvider, ParsedFrame
from .schema import LiveVesselObservation, TrajectoryPoint, VesselState
from .store import LiveVesselStore

__all__ = [
    "AisIngestConsumer",
    "IngestHealth",
    "OpenWatersProvider",
    "LiveAisProvider",
    "ParsedFrame",
    "BoundingBox",
    "TAIWAN_BBOX",
    "LiveVesselObservation",
    "TrajectoryPoint",
    "VesselState",
    "LiveVesselStore",
    "get_store",
    "get_consumer",
    "reset_live_state",
]

# Process-wide singletons. One upstream feed -> one store -> many API reads.
_store: LiveVesselStore | None = None
_consumer: AisIngestConsumer | None = None


def get_store() -> LiveVesselStore:
    global _store
    if _store is None:
        _store = LiveVesselStore()
    return _store


def get_consumer() -> AisIngestConsumer:
    global _consumer
    if _consumer is None:
        _consumer = AisIngestConsumer(OpenWatersProvider(), get_store())
    return _consumer


def reset_live_state() -> None:
    """Reset singletons (used by tests to isolate state)."""

    global _store, _consumer
    _store = None
    _consumer = None
