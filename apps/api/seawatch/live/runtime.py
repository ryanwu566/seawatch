"""Process-wide ownership for live source state."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging
from typing import TYPE_CHECKING

from .active_view import ActiveVesselView
from .area_scan import AreaScanService
from .area_scan_access import AreaScanAccessConfig, AreaScanAdmissionController
from .config import LiveRuntimeConfig
from .datalastic import (
    DatalasticAreaScanProvider,
    DatalasticClient,
    DatalasticConfig,
    DatalasticStatusCache,
)
from .edge_ais import EdgeAisDecoder
from .edge_ingest import EdgeAisConsumer
from .identity import VesselIdentityRegistry
from .ingest import AisIngestConsumer
from .open_waters import OpenWatersProvider
from .resilience import ResilienceModeManager, ResilienceStatus, SourceHealthSnapshot
from .store import LiveVesselStore

if TYPE_CHECKING:
    from ..detection.live_runtime import LiveDetectionRuntime


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
    datalastic_config: DatalasticConfig
    datalastic_client: DatalasticClient | None
    datalastic_status: DatalasticStatusCache
    live_detection: LiveDetectionRuntime
    area_scan_service: AreaScanService
    area_scan_access: AreaScanAccessConfig
    area_scan_admission: AreaScanAdmissionController


_runtime: LiveRuntime | None = None


def _build_runtime() -> LiveRuntime:
    from ..detection.live_runtime import LiveDetectionRuntime

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
    datalastic_config = DatalasticConfig.from_env()
    datalastic_client = (
        DatalasticClient(datalastic_config) if datalastic_config.configured else None
    )
    datalastic_provider = (
        DatalasticAreaScanProvider(datalastic_client)
        if datalastic_client is not None
        else None
    )
    datalastic_status = DatalasticStatusCache(
        configured=datalastic_config.configured
    )
    live_detection = LiveDetectionRuntime(identity_registry)

    async def update_live_detection(observations, scanned_at) -> None:
        await asyncio.to_thread(
            live_detection.update,
            observations,
            scanned_at=scanned_at,
        )

    area_scan_access = AreaScanAccessConfig.from_env()
    area_scan_admission = AreaScanAdmissionController(
        max_scans=area_scan_access.max_scans_per_window,
        max_provider_requests=area_scan_access.max_provider_requests_per_window,
        window_seconds=area_scan_access.window_seconds,
    )
    return LiveRuntime(
        cloud=CloudLiveState(store=store, consumer=consumer),
        edge=EdgeLiveState(store=edge_store, consumer=edge_consumer),
        config=config,
        identity_registry=identity_registry,
        active_view=ActiveVesselView(store, edge_store, identity_registry),
        mode_manager=ResilienceModeManager(config),
        datalastic_config=datalastic_config,
        datalastic_client=datalastic_client,
        datalastic_status=datalastic_status,
        live_detection=live_detection,
        area_scan_service=AreaScanService(
            provider=datalastic_provider,
            identity_registry=identity_registry,
            status_cache=datalastic_status,
            admission=area_scan_admission,
            observation_sink=update_live_detection,
        ),
        area_scan_access=area_scan_access,
        area_scan_admission=area_scan_admission,
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


def get_resilience_status(runtime: LiveRuntime | None = None) -> ResilienceStatus:
    active_runtime = runtime or get_live_runtime()
    cloud_store = active_runtime.cloud.store
    edge_store = active_runtime.edge.store
    edge_consumer = active_runtime.edge.consumer
    cloud = SourceHealthSnapshot(
        source="open_waters",
        connected=active_runtime.cloud.consumer.health.connected,
        last_message_at=cloud_store.last_message_at(),
        last_message_monotonic=cloud_store.last_message_monotonic(),
        vessel_count=cloud_store.vessel_count(),
        input_kind=None,
    )
    edge = SourceHealthSnapshot(
        source="edge_ais",
        connected=edge_consumer.health.receiver_active,
        last_message_at=edge_consumer.health.last_valid_ais_at,
        last_message_monotonic=edge_consumer.last_valid_monotonic,
        vessel_count=edge_store.vessel_count(),
        input_kind=edge_consumer.health.input_kind,
    )
    return active_runtime.mode_manager.evaluate(
        cloud,
        edge,
        offline_demo=active_runtime.config.offline_demo,
    )
