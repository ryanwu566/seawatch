"""Phase 9 Resilience Logistics domain contracts.

All entities are plain, frozen, serializable records. Coordinates are WGS84
(EPSG:4326), consistent with the rest of SeaWatch. Every record carries a
``source_type`` provenance label and, where a field is classified ``official``
or ``derived``, adequate :class:`SourceMetadata` that genuinely supports it.

This module is **pure data**: no I/O, no scoring, no Phase 8 imports. The
records are frozen so provenance cannot be mutated or upgraded after creation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class SourceType(str, Enum):
    """Four-level provenance label (design §6).

    - ``official``: published, citable public fact (requires SourceMetadata).
    - ``derived``: computed from an official/public value by a stated method.
    - ``scenario``: a deliberate planning assumption for the demo scenario.
    - ``synthetic``: fabricated placeholder with no real-world claim.
    """

    OFFICIAL = "official"
    DERIVED = "derived"
    SCENARIO = "scenario"
    SYNTHETIC = "synthetic"


class Commodity(str, Enum):
    """Critical civilian commodity classes (design §4)."""

    MEDICAL = "medical"
    FOOD = "food"
    FUEL = "fuel"


@dataclass(frozen=True)
class SourceMetadata:
    """Evidence backing an ``official``/``derived`` classification.

    An ``official`` field requires ``source_name`` and ``source_reference``
    (and ``as_of`` where applicable). A ``derived`` field names its
    ``derivation_method``. No field is upgraded to ``official`` merely because a
    port is a public civilian port; the metadata must genuinely support it.
    """

    source_name: str | None = None
    source_reference: str | None = None
    as_of: str | None = None
    derivation_method: str | None = None


@dataclass(frozen=True)
class Port:
    id: str
    name_zh: str
    name_en: str
    lon: float
    lat: float
    capacity_units: float
    base_handling_cost: float
    source_type: SourceType
    source_metadata: SourceMetadata | None = None


@dataclass(frozen=True)
class Demand:
    id: str
    commodity: Commodity
    priority: int
    quantity_units: float
    origin_demand_node: str
    normally_served_by: str
    source_type: SourceType
    source_metadata: SourceMetadata | None = None


@dataclass(frozen=True)
class Supply:
    id: str
    commodity: Commodity
    available_units: float
    entry_port_options: tuple[str, ...]
    source_type: SourceType
    source_metadata: SourceMetadata | None = None


@dataclass(frozen=True)
class Route:
    id: str
    from_port: str
    to_demand_node: str
    distance_km: float
    baseline_eta_hours: float
    per_unit_cost: float
    route_risk: float
    source_type: SourceType
    path_geometry: dict | None = None
    schematic: bool = False
    source_metadata: SourceMetadata | None = None


@dataclass(frozen=True)
class DisruptionScenario:
    id: str
    name_zh: str
    name_en: str
    disrupted_ports: tuple[str, ...]
    description_zh: str
    description_en: str
    source_type: SourceType
    capacity_overrides: dict[str, float] = field(default_factory=dict)
    source_metadata: SourceMetadata | None = None


@dataclass(frozen=True)
class Assignment:
    """One port/route assignment within an :class:`Allocation`."""

    port_id: str
    route_id: str
    units: float
    eta_hours: float
    cost: float
    risk: float


@dataclass(frozen=True)
class Allocation:
    demand_id: str
    assignments: tuple[Assignment, ...]
    satisfied_units: float
    unmet_units: float
    score: float


@dataclass(frozen=True)
class DecisionBrief:
    scenario_id: str
    summary_zh: str
    summary_en: str
    recommended_allocations: tuple[Allocation, ...]
    alternatives: tuple[dict, ...]
    trade_offs: tuple[str, ...]
    unmet_demand: tuple[dict, ...]
    provenance_note: str
    assumptions: tuple[str, ...]
    provenance_summary: dict[str, int]
