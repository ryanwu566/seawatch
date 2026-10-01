"""Pure contracts for SeaWatch Cloud/Edge resilience state."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


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
