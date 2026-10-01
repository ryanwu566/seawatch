"""Optional localhost UDP and explicit replay ingestion for Edge AIS."""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from dataclasses import replace as dataclass_replace
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import LiveRuntimeConfig
from .edge_ais import EdgeAisDecoder
from .resilience import EdgeInputKind
from .schema import utcnow
from .store import LiveVesselStore

logger = logging.getLogger("seawatch.live.edge_ingest")
_MAX_ERROR_LENGTH = 240


@dataclass
class EdgeIngestHealth:
    receiver_active: bool
    receiver_detected: bool
    input_kind: EdgeInputKind
    bind_host: str
    bind_port: int
    last_nmea_at: datetime | None = None
    last_valid_ais_at: datetime | None = None
    received_messages: int = 0
    decoded_messages: int = 0
    rejected_messages: int = 0
    last_error: str | None = None

    def record_error(self, error: BaseException | str) -> None:
        value = (
            f"{type(error).__name__}: {error}"
            if isinstance(error, BaseException)
            else error
        )
        self.last_error = value[:_MAX_ERROR_LENGTH]

    def snapshot(self, store: LiveVesselStore, now: datetime) -> dict[str, Any]:
        age = None
        if self.last_valid_ais_at is not None:
            age = max(0.0, (now - self.last_valid_ais_at).total_seconds())
        return {
            "receiver_active": self.receiver_active,
            "receiver_detected": self.receiver_detected,
            "input_kind": self.input_kind.value,
            "bind_host": self.bind_host,
            "bind_port": self.bind_port,
            "last_nmea_at": self.last_nmea_at.isoformat() if self.last_nmea_at else None,
            "last_valid_ais_at": self.last_valid_ais_at.isoformat()
            if self.last_valid_ais_at
            else None,
            "message_age_seconds": round(age, 1) if age is not None else None,
            "received_messages": self.received_messages,
            "decoded_messages": self.decoded_messages,
            "rejected_messages": self.rejected_messages,
            "local_vessel_count": store.vessel_count(),
            "last_error": self.last_error,
        }


class _EdgeDatagramProtocol(asyncio.DatagramProtocol):
    def __init__(self, consumer: "EdgeAisConsumer") -> None:
        self._consumer = consumer

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        self._consumer.handle_datagram(data, addr)

    def error_received(self, exc: Exception) -> None:
        self._consumer.health.record_error(exc)


class EdgeAisConsumer:
    """Own exactly one optional Edge input and write only to the Edge store."""

    def __init__(
        self,
        decoder: EdgeAisDecoder,
        store: LiveVesselStore,
        config: LiveRuntimeConfig,
        *,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.decoder = decoder
        self.store = store
        self.config = config
        self.health = EdgeIngestHealth(
            receiver_active=False,
            receiver_detected=False,
            input_kind=EdgeInputKind.DISABLED,
            bind_host=config.edge_host,
            bind_port=config.edge_port,
        )
        self._monotonic = monotonic
        self._sleep = sleep
        self._last_valid_monotonic: float | None = None
        self._task: asyncio.Task[None] | None = None
        self._transport: asyncio.DatagramTransport | None = None
        self._stop = asyncio.Event()

    @property
    def last_valid_monotonic(self) -> float | None:
        return self._last_valid_monotonic

    def start(self) -> None:
        if self._task is not None:
            return
        self._stop.clear()
        if self.config.edge_replay_enabled and self.config.edge_replay_file is not None:
            loop = asyncio.get_event_loop()
            self.health.input_kind = EdgeInputKind.REPLAY
            self.health.receiver_active = True
            self._task = loop.create_task(self._run_replay(), name="seawatch-edge-replay")
        elif self.config.edge_ingest_enabled:
            loop = asyncio.get_event_loop()
            self.health.input_kind = EdgeInputKind.UDP
            self._task = loop.create_task(self._run_udp(), name="seawatch-edge-udp")

    async def stop(self) -> None:
        self._stop.set()
        if self._transport is not None:
            self._transport.close()
            self._transport = None
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
            self._task = None
        self.health.receiver_active = False

    async def _run_udp(self) -> None:
        try:
            loop = asyncio.get_running_loop()
            transport, _ = await loop.create_datagram_endpoint(
                lambda: _EdgeDatagramProtocol(self),
                local_addr=(self.config.edge_host, self.config.edge_port),
            )
            self._transport = transport
            self.health.receiver_active = True
            self.health.last_error = None
            await self._stop.wait()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - bounded health, no retry loop
            self.health.receiver_active = False
            self.health.record_error(exc)
            logger.warning("Edge UDP listener unavailable: %s", self.health.last_error)
        finally:
            if self._transport is not None:
                self._transport.close()
                self._transport = None

    async def _run_replay(self) -> None:
        replay_file = self.config.edge_replay_file
        try:
            if replay_file is None:
                raise FileNotFoundError("edge replay file is not configured")
            lines = [line for line in Path(replay_file).read_bytes().splitlines() if line.strip()]
            if not lines:
                raise ValueError("edge replay file contains no NMEA records")
            while not self._stop.is_set():
                for line in lines:
                    if self._stop.is_set():
                        break
                    self._handle_line(line, replay=True)
                    await self._sleep(self.config.edge_replay_interval_seconds)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - bounded health, no retry loop
            self.health.record_error(exc)
            logger.warning("Edge replay unavailable: %s", self.health.last_error)
        finally:
            self.health.receiver_active = False

    def handle_datagram(self, data: bytes, addr: tuple[str, int]) -> None:
        lines = [line for line in data.splitlines() if line.strip()]
        if not lines and data.strip():
            lines = [data]
        for line in lines:
            self.health.received_messages += 1
            self.health.last_nmea_at = utcnow()
            try:
                sender_is_loopback = ipaddress.ip_address(addr[0]).is_loopback
            except ValueError:
                sender_is_loopback = False
            if not sender_is_loopback:
                self.health.rejected_messages += 1
                self.health.record_error("non-loopback Edge AIS sender rejected")
                continue
            self._decode_line(line, replay=False)

    def _handle_line(self, line: bytes, *, replay: bool) -> None:
        self.health.received_messages += 1
        self.health.last_nmea_at = utcnow()
        self._decode_line(line, replay=replay)

    def _decode_line(self, line: bytes, *, replay: bool) -> None:
        received_at = utcnow()
        result = self.decoder.feed_line(line, received_at=received_at)
        self.health.decoded_messages += result.accepted_frames
        self.health.rejected_messages += result.rejected_frames
        if not result.observations:
            return
        observations = result.observations
        if replay:
            observations = tuple(
                dataclass_replace(observation, source="edge_replay")
                for observation in observations
            )
        self.store.update_many(observations)
        self.health.receiver_detected = True
        self.health.last_valid_ais_at = received_at
        self._last_valid_monotonic = self._monotonic()
