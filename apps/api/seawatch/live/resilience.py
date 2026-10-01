"""Pure contracts for SeaWatch Cloud/Edge resilience state."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import time
from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .config import LiveRuntimeConfig


class OperatingMode(str, Enum):
    CLOUD_LIVE = "CLOUD_LIVE"
    EDGE_LIVE = "EDGE_LIVE"
    EDGE_REPLAY = "EDGE_REPLAY"
    NO_LIVE_SOURCE = "NO_LIVE_SOURCE"
    OFFLINE_DEMO = "OFFLINE_DEMO"


class EdgeInputKind(str, Enum):
    DISABLED = "disabled"
    UDP = "udp"
    REPLAY = "replay"


class CoverageKind(str, Enum):
    CLOUD = "taiwan_wide_network_feed"
    EDGE = "local_rf"
    NONE = "none"
    DEMO = "demo"


class ObservationOrigin(str, Enum):
    CLOUD = "cloud"
    EDGE_RF = "edge_rf"
    EDGE_REPLAY = "edge_replay"
    OFFLINE_DEMO = "offline_demo"


class DisplayState(str, Enum):
    LIVE = "live"
    CACHED = "cached"
    STALE = "stale"


class PowerMode(str, Enum):
    EXTERNAL = "external"
    BATTERY_UPS = "battery_ups"


@dataclass(frozen=True)
class SourceHealthSnapshot:
    """Internal source state used for monotonic freshness decisions."""

    source: str
    connected: bool
    last_message_at: datetime | None
    last_message_monotonic: float | None
    vessel_count: int
    input_kind: EdgeInputKind | None


@dataclass(frozen=True)
class SourceStatus:
    """Computed source status safe for serialization to public health APIs."""

    source: str
    fresh: bool
    message_age_seconds: float | None
    vessel_count: int
    connected: bool
    input_kind: EdgeInputKind | None


@dataclass(frozen=True)
class ResilienceStatus:
    mode: OperatingMode
    coverage: CoverageKind
    simulated: bool
    cloud: SourceStatus
    edge: SourceStatus
    power_mode: PowerMode


class ResilienceModeManager:
    """Select an honest live mode using monotonic freshness and recovery time."""

    def __init__(
        self,
        config: "LiveRuntimeConfig",
        *,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._config = config
        self._monotonic = monotonic
        self._current_mode = OperatingMode.NO_LIVE_SOURCE
        self._cloud_recovery_started_at: float | None = None
        self._last_now: float | None = None

    @property
    def current_mode(self) -> OperatingMode:
        return self._current_mode

    @property
    def cloud_recovery_started_at(self) -> float | None:
        return self._cloud_recovery_started_at

    def _safe_now(self) -> float:
        current = self._monotonic()
        if self._last_now is None:
            self._last_now = current
        else:
            self._last_now = max(self._last_now, current)
        return self._last_now

    @staticmethod
    def _source_status(
        snapshot: SourceHealthSnapshot,
        *,
        now: float,
        stale_seconds: float,
    ) -> SourceStatus:
        age = None
        if snapshot.last_message_monotonic is not None:
            age = max(0.0, now - snapshot.last_message_monotonic)
        return SourceStatus(
            source=snapshot.source,
            fresh=age is not None and age <= stale_seconds,
            message_age_seconds=round(age, 3) if age is not None else None,
            vessel_count=snapshot.vessel_count,
            connected=snapshot.connected,
            input_kind=snapshot.input_kind,
        )

    @staticmethod
    def _edge_mode(edge: SourceStatus) -> OperatingMode:
        if edge.input_kind is EdgeInputKind.REPLAY:
            return OperatingMode.EDGE_REPLAY
        return OperatingMode.EDGE_LIVE

    def evaluate(
        self,
        cloud: SourceHealthSnapshot,
        edge: SourceHealthSnapshot,
        *,
        offline_demo: bool = False,
    ) -> ResilienceStatus:
        now = self._safe_now()
        cloud_status = self._source_status(
            cloud, now=now, stale_seconds=self._config.cloud_stale_seconds
        )
        edge_status = self._source_status(
            edge, now=now, stale_seconds=self._config.edge_stale_seconds
        )

        if offline_demo:
            mode = OperatingMode.OFFLINE_DEMO
            self._cloud_recovery_started_at = None
        elif cloud_status.fresh:
            if self._current_mode in {
                OperatingMode.EDGE_LIVE,
                OperatingMode.EDGE_REPLAY,
            } and edge_status.fresh:
                if self._cloud_recovery_started_at is None:
                    self._cloud_recovery_started_at = now
                recovered_for = max(0.0, now - self._cloud_recovery_started_at)
                mode = (
                    OperatingMode.CLOUD_LIVE
                    if recovered_for >= self._config.cloud_recovery_seconds
                    else self._edge_mode(edge_status)
                )
            else:
                mode = OperatingMode.CLOUD_LIVE
                self._cloud_recovery_started_at = None
        elif edge_status.fresh and edge_status.input_kind in {
            EdgeInputKind.UDP,
            EdgeInputKind.REPLAY,
        }:
            mode = self._edge_mode(edge_status)
            self._cloud_recovery_started_at = None
        else:
            mode = OperatingMode.NO_LIVE_SOURCE
            self._cloud_recovery_started_at = None

        if mode is OperatingMode.CLOUD_LIVE:
            coverage = CoverageKind.CLOUD
        elif mode in {OperatingMode.EDGE_LIVE, OperatingMode.EDGE_REPLAY}:
            coverage = CoverageKind.EDGE
        elif mode is OperatingMode.OFFLINE_DEMO:
            coverage = CoverageKind.DEMO
        else:
            coverage = CoverageKind.NONE

        self._current_mode = mode
        return ResilienceStatus(
            mode=mode,
            coverage=coverage,
            simulated=mode in {OperatingMode.EDGE_REPLAY, OperatingMode.OFFLINE_DEMO},
            cloud=cloud_status,
            edge=edge_status,
            power_mode=self._config.power_mode,
        )
