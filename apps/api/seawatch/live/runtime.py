"""Process-wide ownership for live source state."""

from __future__ import annotations

from dataclasses import dataclass
import logging

from .active_view import ActiveVesselView
from .config import LiveRuntimeConfig
from .edge_ais import EdgeAisDecoder
from .edge_ingest import EdgeAisConsumer
from .identity import VesselIdentityRegistry
from .ingest import AisIngestConsumer
from .open_waters import OpenWatersProvider
from .resilience import ResilienceModeManager
from .store import LiveVesselStore


@dataclass(frozen=True)
class CloudLiveState:
    """The Cloud store and the sole consumer that writes to it."""

    store: LiveVesselStore
    consumer: AisIngestConsumer


@dataclass(frozen=True)
class EdgeLiveState:
    """The Edge store and its optional local-only consumer."""

    store: LiveVesselStore
    consumer: EdgeAisConsumer


@dataclass(frozen=True)
class LiveRuntime:
    """Process-wide live services, beginning with the existing Cloud source."""

    cloud: CloudLiveState
    edge: EdgeLiveState
    config: LiveRuntimeConfig
    identity_registry: VesselIdentityRegistry
    active_view: ActiveVesselView
    mode_manager: ResilienceModeManager


_runtime: LiveRuntime | None = None


def _build_runtime() -> LiveRuntime:
    config = LiveRuntimeConfig.from_env()
    for warning in config.warnings:
        logging.getLogger("seawatch.live.runtime").warning("%s", warning)
    if config.identity_key is None:
        logging.getLogger("seawatch.live.runtime").warning(
            "SEAWATCH_IDENTITY_KEY is unset; public vessel IDs reset on restart"
        )
    store = LiveVesselStore()
    consumer = AisIngestConsumer(OpenWatersProvider(), store)
    edge_store = LiveVesselStore()
    edge_consumer = EdgeAisConsumer(EdgeAisDecoder(), edge_store, config)
    identity_registry = VesselIdentityRegistry(config.identity_key)
    return LiveRuntime(
        cloud=CloudLiveState(store=store, consumer=consumer),
        edge=EdgeLiveState(store=edge_store, consumer=edge_consumer),
        config=config,
        identity_registry=identity_registry,
        active_view=ActiveVesselView(store, identity_registry),
        mode_manager=ResilienceModeManager(config),
    )


def get_live_runtime() -> LiveRuntime:
    global _runtime
    if _runtime is None:
        _runtime = _build_runtime()
    return _runtime


def reset_live_runtime() -> None:
    """Replace process-wide live state on its next access (primarily for tests)."""

    global _runtime
    _runtime = None
