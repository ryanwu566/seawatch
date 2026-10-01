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
from .runtime import (
    CloudLiveState,
    EdgeLiveState,
    LiveRuntime,
    get_live_runtime,
    reset_live_runtime,
)
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
    "CloudLiveState",
    "EdgeLiveState",
    "LiveRuntime",
    "get_live_runtime",
    "reset_live_runtime",
    "get_store",
    "get_consumer",
    "reset_live_state",
]


def get_store() -> LiveVesselStore:
    """Compatibility alias for the Cloud-owned store."""

    return get_live_runtime().cloud.store


def get_consumer() -> AisIngestConsumer:
    """Compatibility alias for the Cloud-owned consumer."""

    return get_live_runtime().cloud.consumer


def reset_live_state() -> None:
    """Reset singletons (used by tests to isolate state)."""

    reset_live_runtime()
