"""Pure, deterministic maritime GIS context resolver.

Reuses :func:`apps.api.seawatch.trajectories.geodesy.geodesic_distance_m`
(WGS84) for distances and Shapely for point-in-polygon containment. No I/O, no
network, no state: same position + same bundled reference data ⇒ identical
output.

Scope (P0 only): distance to coast, nearest civilian port + distance, named
maritime area containment. It performs no violation detection, no restricted
-area judgement, no legality inference, no TSS rules, no military areas, and
draws no autonomous conclusion.
"""

from __future__ import annotations

import math

from shapely.geometry import Point, Polygon

from ...trajectories.geodesy import geodesic_distance_m
from . import reference
from .schema import GeographicContext, NamedAreaHit, Provenanced

SCHEMA_VERSION = "gis-context-1"

# Densification step so a nearest-vertex search on a coarse ring approximates the
# true perpendicular distance to the coastline. Degrees of lon/lat spacing.
_COAST_DENSIFY_DEG = 0.02


def _unknown(note: str) -> GeographicContext:
    """A fully-unknown result: position null or outside reference coverage."""

    reason = Provenanced(None, "unknown", note=note)
    return GeographicContext(
        schema_version=SCHEMA_VERSION,
        coverage=reason,
        distance_to_coast_km=Provenanced(None, "unknown", note=note),
        nearest_port=Provenanced(None, "unknown", note=note),
        within_named_areas=(),
        named_areas_computed=False,
    )


def _densify_ring(ring: tuple[tuple[float, float], ...]) -> list[tuple[float, float]]:
    """Insert intermediate vertices so nearest-vertex ≈ nearest-point."""

    if len(ring) < 2:
        return list(ring)
    dense: list[tuple[float, float]] = []
    for i in range(1, len(ring)):
        a = ring[i - 1]
        b = ring[i]
        seg = math.hypot(b[0] - a[0], b[1] - a[1])
        steps = max(1, int(seg / _COAST_DENSIFY_DEG))
        for k in range(steps):
            t = k / steps
            dense.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
    dense.append(ring[-1])
    return dense


def _distance_to_coast_km(lon: float, lat: float) -> float:
    """Minimum WGS84 geodesic distance (km) from a position to any coastline ring.

    Nearest vertex over densified rings, then an exact geodesic distance to that
    vertex. Deterministic.
    """

    best_m: float | None = None
    for ring in reference.COASTLINE_RINGS:
        for vlon, vlat in _densify_ring(ring):
            d = geodesic_distance_m(lon, lat, vlon, vlat)
            if best_m is None or d < best_m:
                best_m = d
    assert best_m is not None  # reference always has coastline geometry
    return best_m / 1000.0


def _nearest_port(lon: float, lat: float) -> dict:
    """Nearest civilian port and its geodesic distance (km).

    Deterministic tie-break by port id so identical distances resolve stably.
    """

    best: tuple[float, str, reference.PortRef] | None = None
    for port in reference.PORTS:
        d_km = geodesic_distance_m(lon, lat, port.lon, port.lat) / 1000.0
        key = (d_km, port.id)
        if best is None or key < (best[0], best[1]):
            best = (d_km, port.id, port)
    assert best is not None
    d_km, _, port = best
    return {
        "id": port.id,
        "name_zh": port.name_zh,
        "name_en": port.name_en,
        "distance_km": round(d_km, 2),
    }


def _within_named_areas(lon: float, lat: float) -> tuple[NamedAreaHit, ...]:
    """All named maritime areas whose polygon contains the position.

    A position may be within zero, one, or several areas; all are reported.
    Containment is a place fact and carries no permission semantics.
    """

    point = Point(lon, lat)
    hits: list[NamedAreaHit] = []
    for area in reference.MARITIME_AREAS:
        polygon = Polygon(area.ring)
        # ``covers`` includes boundary; deterministic point-in-polygon.
        if polygon.covers(point):
            hits.append(
                NamedAreaHit(
                    id=area.id,
                    name_zh=area.name_zh,
                    name_en=area.name_en,
                    kind=area.kind,  # type: ignore[arg-type]
                    source=reference.AREAS_SOURCE,
                )
            )
    # Deterministic ordering by id.
    hits.sort(key=lambda h: h.id)
    return tuple(hits)


def resolve_geographic_context(
    lon: float | None, lat: float | None
) -> GeographicContext:
    """Resolve geographic context facts for a vessel position.

    Returns a fully-``unknown`` result when the position is missing, non-finite,
    or outside the reference coverage bbox — never a guessed value.
    """

    if lon is None or lat is None:
        return _unknown("no position available")
    if not (math.isfinite(lon) and math.isfinite(lat)):
        return _unknown("non-finite position")
    if not reference.in_bbox(lon, lat):
        return _unknown("position outside reference coverage")

    coast_km = _distance_to_coast_km(lon, lat)
    port = _nearest_port(lon, lat)
    areas = _within_named_areas(lon, lat)

    return GeographicContext(
        schema_version=SCHEMA_VERSION,
        coverage=Provenanced("in_coverage", "derived", source=None),
        distance_to_coast_km=Provenanced(
            round(coast_km, 2),
            "derived",
            source=reference.COASTLINE_SOURCE,
            note="nearest-point WGS84 geodesic distance to coastline",
        ),
        nearest_port=Provenanced(
            port,
            "derived",
            source=reference.PORTS_SOURCE,
            note="port name/location official; distance derived (WGS84)",
        ),
        within_named_areas=areas,
        named_areas_computed=True,
    )
