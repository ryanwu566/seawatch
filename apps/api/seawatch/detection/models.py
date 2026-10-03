"""Core data model for the detection stack.

Everything here is neutral behavioural vocabulary. Events and alerts are
*candidates for human review*; nothing in this package asserts intent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np


@dataclass
class Track:
    """One AIS identity's reported positions, time-sorted. Times are epoch seconds."""

    mmsi: str
    name: str
    ship_type: str  # cargo | tanker | ferry | fishing | passenger | other
    flag: str
    t: np.ndarray
    lat: np.ndarray
    lon: np.ndarray
    sog: np.ndarray  # reported speed over ground, knots (nan if missing)
    cog: np.ndarray  # reported course over ground, degrees (nan if missing)
    status: np.ndarray | None = None  # AIS navigational status code per report (None = not available)

    def __len__(self) -> int:
        return int(self.t.size)

    def slice(self, i0: int, i1: int) -> "Track":
        s = slice(i0, i1)
        return Track(self.mmsi, self.name, self.ship_type, self.flag,
                     self.t[s], self.lat[s], self.lon[s], self.sog[s], self.cog[s],
                     None if self.status is None else self.status[s])


@dataclass(frozen=True)
class Zone:
    """A named area of interest (lat, lon vertices)."""

    id: str
    name: str
    kind: str  # protected | cable | restricted | port | anchorage | fishing_ground
    polygon: list[tuple[float, float]]
    description: str = ""
    sensitivity: float = 1.0  # 0..1 weight used when scoring entries


@dataclass(frozen=True)
class Receiver:
    """Terrestrial AIS receiver: coverage is modelled as a disc."""

    id: str
    lat: float
    lon: float
    range_nm: float = 45.0


@dataclass
class Event:
    """A single detected behaviour with its evidence."""

    id: str
    kind: str  # ais_gap | loitering | rendezvous | cluster | zone_entry | position_jump | identity_conflict | route_deviation
    mmsis: list[str]
    t_start: float
    t_end: float
    lat: float
    lon: float
    severity: float  # 0..100, detector-local strength
    confidence: float  # 0..1, evidence quality
    summary: str
    evidence: list[str] = field(default_factory=list)  # human-readable reasons
    benign_explanations: list[str] = field(default_factory=list)
    uncertainty: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    zone_id: str | None = None
    path: list[tuple[float, float]] = field(default_factory=list)  # (lat, lon) for map drawing

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "kind": self.kind, "mmsis": self.mmsis,
            "t_start": self.t_start, "t_end": self.t_end,
            "lat": round(self.lat, 5), "lon": round(self.lon, 5),
            "severity": round(self.severity, 1), "confidence": round(self.confidence, 2),
            "summary": self.summary, "evidence": self.evidence,
            "benign_explanations": self.benign_explanations,
            "uncertainty": self.uncertainty, "metrics": self.metrics,
            "zone_id": self.zone_id, "path": [[round(a, 5), round(b, 5)] for a, b in self.path],
        }


@dataclass(frozen=True)
class TruthEvent:
    """Ground-truth label injected by the simulator."""

    id: str
    kind: str
    mmsis: tuple[str, ...]
    t_start: float
    t_end: float
    note: str = ""
    benign: bool = False  # True => a deliberately benign look-alike (should NOT alert)


@dataclass
class Scenario:
    """A complete simulated world: tracks, areas, receivers and labelled truth."""

    name: str
    t0: float
    t1: float
    tracks: list[Track]
    zones: list[Zone]
    receivers: list[Receiver]
    truth: list[TruthEvent]
    seed: int = 0
