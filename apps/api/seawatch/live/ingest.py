"""Long-running server-side AIS ingest consumer.

One background asyncio task owns the single upstream WebSocket connection,
subscribes to the Taiwan bounding box, normalizes frames through the active
provider, and writes them into the shared :class:`LiveVesselStore`. On
disconnect it reconnects with exponential backoff while preserving the last
known vessel snapshot (the store is never cleared on disconnect).

Design constraints honored:
- Never blocks FastAPI startup forever: the task is launched fire-and-forget and
  connection happens in the background.
- Survives provider disconnects and transient errors.
- Exposes a health snapshot for ``GET /live/health``.
- Credentials (if a provider needs them) are read from the environment by the
  provider, never logged or returned.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .provider import TAIWAN_BBOX, BoundingBox, LiveAisProvider
from .schema import utcnow
from .store import LiveVesselStore

logger = logging.getLogger("seawatch.live.ingest")

try:  # websockets is required only when the consumer actually connects.
    import websockets
except ImportError:  # pragma: no cover - exercised only without the dependency
    websockets = None  # type: ignore[assignment]


@dataclass
class IngestHealth:
    """Mutable health snapshot shared with the API layer."""

    provider: str
    connected: bool = False
    last_connect_at: datetime | None = None
    last_disconnect_at: datetime | None = None
    last_error: str | None = None
    reconnect_attempts: int = 0
    subscribed: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "connected": self.connected,
            "subscribed": self.subscribed,
            "last_connect_at": self.last_connect_at.isoformat() if self.last_connect_at else None,
            "last_disconnect_at": self.last_disconnect_at.isoformat()
            if self.last_disconnect_at
            else None,
            "reconnect_attempts": self.reconnect_attempts,
            "last_error": self.last_error,
        }


class AisIngestConsumer:
    """Owns the upstream connection and feeds the live store."""

    def __init__(
        self,
        provider: LiveAisProvider,
        store: LiveVesselStore,
        *,
        bbox: BoundingBox = TAIWAN_BBOX,
        initial_backoff: float = 1.0,
        max_backoff: float = 30.0,
        cleanup_interval: float = 60.0,
    ) -> None:
        self.provider = provider
        self.store = store
        self.bbox = bbox
        self.health = IngestHealth(provider=provider.name)
        self._initial_backoff = initial_backoff
        self._max_backoff = max_backoff
        self._cleanup_interval = cleanup_interval
        self._task: asyncio.Task[None] | None = None
        self._cleanup_task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()

    # -- lifecycle --------------------------------------------------------- #
    def start(self) -> None:
        """Launch the background ingest + cleanup tasks (non-blocking)."""

        if self._task is not None:
            return
        self._stop.clear()
        loop = asyncio.get_event_loop()
        self._task = loop.create_task(self._run(), name="seawatch-ais-ingest")
        self._cleanup_task = loop.create_task(
            self._run_cleanup(), name="seawatch-ais-cleanup"
        )

    async def stop(self) -> None:
        """Signal shutdown and wait briefly for tasks to unwind."""

        self._stop.set()
        for task in (self._task, self._cleanup_task):
            if task is not None:
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):  # noqa: BLE001
                    pass
        self._task = None
        self._cleanup_task = None

    # -- background loops -------------------------------------------------- #
    async def _run(self) -> None:
        if websockets is None:
            self.health.last_error = "websockets package not installed"
            logger.warning("Live ingest disabled: websockets package missing")
            return
        if self.provider.requires_credentials():
            # Provider is responsible for sourcing creds from env; if it can't,
            # we do not spin a hot reconnect loop forever.
            logger.info("Provider %s requires credentials", self.provider.name)

        backoff = self._initial_backoff
        while not self._stop.is_set():
            try:
                await self._connect_once()
                backoff = self._initial_backoff  # reset after a clean session
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - any upstream failure -> reconnect
                self.health.connected = False
                self.health.subscribed = False
                self.health.last_error = f"{type(exc).__name__}: {exc}"
                self.health.last_disconnect_at = utcnow()
                logger.warning("AIS ingest error, reconnecting: %s", self.health.last_error)
            if self._stop.is_set():
                break
            self.health.reconnect_attempts += 1
            await asyncio.wait([asyncio.create_task(self._stop.wait())], timeout=backoff)
            backoff = min(self._max_backoff, backoff * 2)

    async def _connect_once(self) -> None:
        url = self.provider.websocket_url
        subscription = self.provider.subscription_message(self.bbox)
        async with websockets.connect(url, open_timeout=10, ping_interval=20) as ws:
            self.health.connected = True
            self.health.last_connect_at = utcnow()
            self.health.last_error = None
            # Subscription must be sent promptly after connecting.
            await ws.send(json.dumps(subscription))
            self.health.subscribed = True
            while not self._stop.is_set():
                raw = await ws.recv()
                self._handle_raw(raw)
        self.health.connected = False
        self.health.last_disconnect_at = utcnow()

    def _handle_raw(self, raw: Any) -> None:
        try:
            frame = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return
        parsed = self.provider.parse_frame(frame)
        if parsed.kind == "position" and parsed.observation is not None:
            self.store.update(parsed.observation)

    async def _run_cleanup(self) -> None:
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._cleanup_interval)
            except asyncio.TimeoutError:
                removed = self.store.cleanup_stale()
                if removed:
                    logger.debug("Removed %d stale vessels", removed)
            except asyncio.CancelledError:
                raise

    # -- health ------------------------------------------------------------ #
    def health_snapshot(self) -> dict[str, Any]:
        last_message_at = self.store.last_message_at()
        age = None
        if last_message_at is not None:
            age = max(0.0, (utcnow() - last_message_at).total_seconds())
        status = "online" if self.health.connected else "degraded"
        if not self.health.connected and self.store.vessel_count() == 0:
            status = "offline"
        return {
            "status": status,
            "provider": self.provider.name,
            "connected": self.health.connected,
            "subscribed": self.health.subscribed,
            "last_message_at": last_message_at.isoformat() if last_message_at else None,
            "message_age_seconds": round(age, 1) if age is not None else None,
            "vessel_count": self.store.vessel_count(),
            "reconnect_attempts": self.health.reconnect_attempts,
            "last_error": self.health.last_error,
            "bbox": {
                "min_lat": self.bbox.min_lat,
                "min_lon": self.bbox.min_lon,
                "max_lat": self.bbox.max_lat,
                "max_lon": self.bbox.max_lon,
            },
        }
