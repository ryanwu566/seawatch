"""SeaWatch dashboard API application factory.

Read-only FastAPI surface over existing Phase 3B explainable review-ranking
outputs. It performs no ranking computation and modifies no Phase 1-3 artifacts.
"""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from contextlib import suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import alerts, context, detection, health, historical, live, logistics, resilience, tracks
from .live import get_live_runtime
from .live.config import LiveRuntimeConfig
from .live.datalastic import ProviderError, ProviderErrorCategory
from .web.serving import configure_local_web

logger = logging.getLogger("seawatch.main")

_TITLE = "SeaWatch API"
_DESCRIPTION = (
    "Read-only access to SeaWatch explainable maritime review-ranking outputs. "
    "Alerts are behavioral review candidates for human review, not threat, "
    "hostility, or legality determinations."
)
_VERSION = "0.1.0"

# The dashboard runs on the Vite dev server (default port 5173) on a different
# origin than the API (port 8000). Browsers require the API to return CORS
# headers or they block the JS from reading the response. Origins can be
# overridden via SEAWATCH_CORS_ORIGINS (comma-separated).
_DEFAULT_CORS_ORIGINS = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
)


def _cors_origins() -> list[str]:
    raw = os.environ.get("SEAWATCH_CORS_ORIGINS")
    if raw:
        origins = [origin.strip() for origin in raw.split(",") if origin.strip()]
        if origins:
            return origins
    return list(_DEFAULT_CORS_ORIGINS)


def _live_ingest_enabled() -> bool:
    """Whether to start the background AIS ingest consumer on startup.

    Off by default so the test suite and offline runs never open sockets. Enable
    with SEAWATCH_LIVE_INGEST=true (or 1/yes/on) when running the live backend.
    """

    return os.environ.get("SEAWATCH_LIVE_INGEST", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


async def _probe_datalastic_status(runtime) -> None:
    """Run one sanitized status probe without affecting application startup."""

    client = runtime.datalastic_client
    if client is None:
        return
    try:
        provider_status = await client.stat()
    except ProviderError as exc:
        runtime.datalastic_status.record_failure(exc.category)
        logger.warning("Datalastic status probe failed (%s)", exc.category.value)
    except Exception:  # noqa: BLE001 - no raw external errors may reach logs
        runtime.datalastic_status.record_failure(ProviderErrorCategory.CONNECTION)
        logger.warning("Datalastic status probe failed (connection)")
    else:
        runtime.datalastic_status.record_success(provider_status)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Start/stop independent Cloud and explicitly enabled Edge consumers."""

    if os.environ.get("SEAWATCH_WARM_DETECTION", "true").strip().lower() in {"1", "true", "yes", "on"}:
        import threading

        def _warm() -> None:
            try:
                from .detection.service import get_service

                svc = get_service()
                svc.alerts()  # builds the scenario and runs detection once so the first screen opens instantly
                logger.info("Detection service ready (region=%s)", svc.region)
            except Exception as exc:  # noqa: BLE001 - monitoring UI must start even if the data is missing
                logger.warning("Detection warm-up failed: %s", exc)

        threading.Thread(target=_warm, daemon=True, name="detection-warmup").start()

    runtime = get_live_runtime()
    consumer = None
    edge_consumer = None
    datalastic_probe = None
    if runtime.datalastic_client is not None:
        datalastic_probe = asyncio.create_task(_probe_datalastic_status(runtime))
    if _live_ingest_enabled():
        consumer = get_live_runtime().cloud.consumer
        try:
            consumer.start()
            logger.info("Live AIS ingest started (provider=%s)", consumer.provider.name)
        except Exception as exc:  # noqa: BLE001 - never block startup on ingest
            logger.warning("Failed to start live AIS ingest: %s", exc)
    if runtime.config.edge_ingest_enabled or runtime.config.edge_replay_enabled:
        edge_consumer = runtime.edge.consumer
        try:
            edge_consumer.start()
            logger.info(
                "Edge AIS ingest starting (input=%s)",
                edge_consumer.health.input_kind.value,
            )
        except Exception as exc:  # noqa: BLE001 - Edge cannot block API/Cloud
            edge_consumer.health.record_error(exc)
            logger.warning("Failed to start Edge AIS ingest: %s", exc)
    try:
        yield
    finally:
        if datalastic_probe is not None:
            if not datalastic_probe.done():
                datalastic_probe.cancel()
            with suppress(asyncio.CancelledError):
                await datalastic_probe
        if runtime.datalastic_client is not None:
            await runtime.datalastic_client.aclose()
        if consumer is not None:
            await consumer.stop()
            logger.info("Live AIS ingest stopped")
        if edge_consumer is not None:
            await edge_consumer.stop()
            logger.info("Edge AIS ingest stopped")


def create_app() -> FastAPI:
    """Build and configure the SeaWatch dashboard API application."""

    app = FastAPI(
        title=_TITLE,
        description=_DESCRIPTION,
        version=_VERSION,
        lifespan=_lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins(),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT"],
        allow_headers=["*"],
    )
    app.include_router(health.router)
    app.include_router(tracks.router)
    app.include_router(alerts.router)
    app.include_router(live.router)
    app.include_router(resilience.router)
    app.include_router(logistics.router)
    app.include_router(context.router)
    app.include_router(historical.router)
    app.include_router(detection.router)
    configure_local_web(app, LiveRuntimeConfig.from_env())
    return app


app = create_app()
