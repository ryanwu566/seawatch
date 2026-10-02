"""Maritime GIS context (P0).

Pure, deterministic geometry over bundled, public, civilian reference data:

* distance to coastline (``derived``),
* nearest civilian port + distance (port name ``official``, distance ``derived``),
* named maritime area containment (area definition ``official``, containment
  ``derived``).

Hard boundaries (enforced by tests):

* No violation detection, restricted-area judgement, or legality inference.
* No TSS rules, no military areas, no autonomous conclusions.
* Named-area containment carries NO permission semantics; it is a place fact.
* Anything unavailable (null/out-of-coverage position) is ``unknown``, never
  guessed.
"""

from .resolver import resolve_geographic_context
from .schema import GeographicContext, NamedAreaHit, Provenance, Provenanced

__all__ = [
    "resolve_geographic_context",
    "GeographicContext",
    "NamedAreaHit",
    "Provenance",
    "Provenanced",
]
