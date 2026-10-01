"""Process-wide ownership for live source state."""

from __future__ import annotations

from dataclasses import dataclass

from .ingest import AisIngestConsumer
from .open_waters import OpenWatersProvider
from .store import LiveVesselStore


@dataclass(frozen=True)
class CloudLiveState:
    """The Cloud store and the sole consumer that writes to it."""

    store: LiveVesselStore
    consumer: AisIngestConsumer


@dataclass(frozen=True)
class LiveRuntime:
    """Process-wide live services, beginning with the existing Cloud source."""

    cloud: CloudLiveState


_runtime: LiveRuntime | None = None


def _build_runtime() -> LiveRuntime:
    store = LiveVesselStore()
    consumer = AisIngestConsumer(OpenWatersProvider(), store)
    return LiveRuntime(cloud=CloudLiveState(store=store, consumer=consumer))


def get_live_runtime() -> LiveRuntime:
    global _runtime
    if _runtime is None:
        _runtime = _build_runtime()
    return _runtime


def reset_live_runtime() -> None:
    """Replace process-wide live state on its next access (primarily for tests)."""

    global _runtime
    _runtime = None
