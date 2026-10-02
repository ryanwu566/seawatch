"""Provenance schema for maritime GIS context.

Mirrors the provenance discipline of
``apps/api/seawatch/trajectories/route_deviation.py``:

* ``Provenance`` is one of ``official`` | ``derived`` | ``unknown`` for this
  layer (``observed`` is intentionally not produced here — the vessel position
  itself is labeled ``observed`` elsewhere; this layer only turns a position
  into ``official``-referenced and ``derived`` facts).
* ``Provenanced.value is None`` always implies ``unknown``.
* Nothing is fabricated: an unavailable fact is ``unknown``, never guessed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Provenance = Literal["official", "derived", "unknown"]

#: Kinds of named maritime area. Descriptive labels for the human reviewer only
#: — NOT a rule/permission classification. No military or restricted kinds.
NamedAreaKind = Literal["anchorage", "approach", "fairway", "port_area"]


@dataclass(frozen=True)
class Provenanced:
    """A value plus how it is known. ``value is None`` ⇒ provenance ``unknown``."""

    value: object
    provenance: Provenance
    #: Cited reference dataset for ``official`` facts, or how a ``derived`` value
    #: was computed. ``None`` for ``unknown``.
    source: str | None = None
    note: str | None = None

    def to_dict(self) -> dict:
        out: dict = {"value": self.value, "provenance": self.provenance}
        if self.source is not None:
            out["source"] = self.source
        if self.note is not None:
            out["note"] = self.note
        return out


@dataclass(frozen=True)
class NamedAreaHit:
    """A named maritime area that contains the position (a place fact)."""

    id: str
    name_zh: str
    name_en: str
    kind: NamedAreaKind
    #: Area definition is ``official`` reference data; the containment test that
    #: produced this hit is ``derived``. Both are recorded for honesty.
    definition_provenance: Provenance = "official"
    containment_provenance: Provenance = "derived"
    source: str | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name_zh": self.name_zh,
            "name_en": self.name_en,
            "kind": self.kind,
            "definition_provenance": self.definition_provenance,
            "containment_provenance": self.containment_provenance,
            **({"source": self.source} if self.source is not None else {}),
        }


_DISCLAIMER = (
    "Geographic context for human review only: geometric facts about the area "
    "around the vessel position, not a judgement about the vessel, its "
    "behavior, its intent, or its permission to be there."
)


@dataclass(frozen=True)
class GeographicContext:
    """The ``gis-context-1`` result for one position.

    ``coverage.value == "in_coverage"`` means the position was inside the
    reference bbox and geometry was computed. Otherwise every field is
    ``unknown``.

    ``within_named_areas`` is a (possibly empty) tuple. An **empty** tuple means
    "computed, inside no named area" (a real ``derived`` result) and is
    deliberately distinct from ``unknown`` ("could not compute").
    """

    schema_version: str
    coverage: Provenanced  # value: "in_coverage" | None(unknown)
    distance_to_coast_km: Provenanced  # derived | unknown
    nearest_port: Provenanced  # value: {id,name_zh,name_en,distance_km} | None
    within_named_areas: tuple[NamedAreaHit, ...] = field(default_factory=tuple)
    #: True only when coverage is in_coverage (areas were actually tested).
    named_areas_computed: bool = False
    disclaimer: str = _DISCLAIMER

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "coverage": self.coverage.to_dict(),
            "distance_to_coast_km": self.distance_to_coast_km.to_dict(),
            "nearest_port": self.nearest_port.to_dict(),
            "within_named_areas": [a.to_dict() for a in self.within_named_areas],
            "named_areas_computed": self.named_areas_computed,
            "disclaimer": self.disclaimer,
        }
