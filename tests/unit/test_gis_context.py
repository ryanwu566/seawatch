"""Unit tests for maritime GIS context (P0).

Covers deterministic geometry, provenance correctness (official / derived /
unknown), the unknown-vs-empty distinction, nearest-port selection, named-area
containment, a language guard (no violation/legality/threat wording), and the
read-only endpoint. No network, no DB, no live-store coupling.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from apps.api.seawatch.context.gis import resolve_geographic_context
from apps.api.seawatch.context.gis import reference
from apps.api.seawatch.context.gis.resolver import SCHEMA_VERSION
from apps.api.seawatch.main import create_app
from apps.api.seawatch.trajectories.geodesy import geodesic_distance_m


# A position inside the Kaohsiung approach + anchorage A (ports/areas chosen so
# containment and nearest-port are both exercised).
KAOHSIUNG_IN_ANCHORAGE = (120.23, 22.575)
# Open water in the Taiwan Strait, inside bbox, inside no named area.
STRAIT_OPEN_WATER = (119.9, 24.0)
# Outside the reference coverage bbox.
OUT_OF_COVERAGE = (140.0, 10.0)


@pytest.fixture()
def client():
    with TestClient(create_app()) as c:
        yield c


# --------------------------------------------------------------------------- #
# Coverage / unknown handling
# --------------------------------------------------------------------------- #


def test_null_position_is_fully_unknown() -> None:
    ctx = resolve_geographic_context(None, None)
    assert ctx.coverage.provenance == "unknown"
    assert ctx.distance_to_coast_km.provenance == "unknown"
    assert ctx.distance_to_coast_km.value is None
    assert ctx.nearest_port.provenance == "unknown"
    assert ctx.nearest_port.value is None
    assert ctx.within_named_areas == ()
    assert ctx.named_areas_computed is False


def test_non_finite_position_is_unknown() -> None:
    ctx = resolve_geographic_context(float("nan"), 23.0)
    assert ctx.coverage.provenance == "unknown"
    assert ctx.named_areas_computed is False


def test_out_of_coverage_position_is_unknown_not_guessed() -> None:
    ctx = resolve_geographic_context(*OUT_OF_COVERAGE)
    assert ctx.coverage.provenance == "unknown"
    assert ctx.distance_to_coast_km.value is None
    assert ctx.nearest_port.value is None
    assert ctx.named_areas_computed is False


# --------------------------------------------------------------------------- #
# Unknown vs empty distinction
# --------------------------------------------------------------------------- #


def test_in_coverage_inside_no_area_is_empty_not_unknown() -> None:
    ctx = resolve_geographic_context(*STRAIT_OPEN_WATER)
    # Computed (not unknown)...
    assert ctx.coverage.value == "in_coverage"
    assert ctx.named_areas_computed is True
    assert ctx.distance_to_coast_km.provenance == "derived"
    # ...but inside no named area → EMPTY, distinct from unknown.
    assert ctx.within_named_areas == ()


def test_out_of_coverage_areas_are_unknown_not_empty() -> None:
    ctx = resolve_geographic_context(*OUT_OF_COVERAGE)
    assert ctx.named_areas_computed is False  # could not compute
    assert ctx.within_named_areas == ()


# --------------------------------------------------------------------------- #
# Provenance correctness
# --------------------------------------------------------------------------- #


def test_provenance_official_derived_unknown_mapping() -> None:
    ctx = resolve_geographic_context(*KAOHSIUNG_IN_ANCHORAGE)
    # Distances / containment are derived.
    assert ctx.distance_to_coast_km.provenance == "derived"
    assert ctx.nearest_port.provenance == "derived"
    # Nearest-port carries the official port reference source.
    assert ctx.nearest_port.source == reference.PORTS_SOURCE
    # Named-area hits: definition official, containment derived.
    assert ctx.within_named_areas, "expected at least one containing area"
    for hit in ctx.within_named_areas:
        assert hit.definition_provenance == "official"
        assert hit.containment_provenance == "derived"
    # No provenance value outside the allowed set.
    allowed = {"official", "derived", "unknown"}
    assert ctx.distance_to_coast_km.provenance in allowed
    assert ctx.nearest_port.provenance in allowed


# --------------------------------------------------------------------------- #
# Distance correctness / determinism
# --------------------------------------------------------------------------- #


def test_nearest_port_matches_independent_geodesic_distance() -> None:
    lon, lat = KAOHSIUNG_IN_ANCHORAGE
    ctx = resolve_geographic_context(lon, lat)
    port = ctx.nearest_port.value
    assert port["id"] == "kaohsiung"
    kao = next(p for p in reference.PORTS if p.id == "kaohsiung")
    expected_km = geodesic_distance_m(lon, lat, kao.lon, kao.lat) / 1000.0
    assert port["distance_km"] == pytest.approx(expected_km, abs=0.01)


def test_each_port_is_its_own_nearest_when_queried_at_its_location() -> None:
    for p in reference.PORTS:
        ctx = resolve_geographic_context(p.lon, p.lat)
        assert ctx.nearest_port.value["id"] == p.id
        assert ctx.nearest_port.value["distance_km"] == pytest.approx(0.0, abs=0.01)


def test_resolver_is_deterministic() -> None:
    a = resolve_geographic_context(*KAOHSIUNG_IN_ANCHORAGE).to_dict()
    b = resolve_geographic_context(*KAOHSIUNG_IN_ANCHORAGE).to_dict()
    assert a == b


def test_distance_to_coast_is_nonnegative_km() -> None:
    ctx = resolve_geographic_context(*STRAIT_OPEN_WATER)
    assert ctx.distance_to_coast_km.value >= 0.0


# --------------------------------------------------------------------------- #
# Named-area containment
# --------------------------------------------------------------------------- #


def test_point_inside_area_reports_that_area() -> None:
    ctx = resolve_geographic_context(*KAOHSIUNG_IN_ANCHORAGE)
    ids = {h.id for h in ctx.within_named_areas}
    # Inside both the approach and the nested anchorage A.
    assert "kaohsiung-approach" in ids
    assert "kaohsiung-anchorage-a" in ids


def test_point_outside_all_areas_reports_none() -> None:
    ctx = resolve_geographic_context(*STRAIT_OPEN_WATER)
    assert ctx.within_named_areas == ()


def test_area_hits_are_sorted_deterministically() -> None:
    ctx = resolve_geographic_context(*KAOHSIUNG_IN_ANCHORAGE)
    ids = [h.id for h in ctx.within_named_areas]
    assert ids == sorted(ids)


# --------------------------------------------------------------------------- #
# Language guard — no violation / legality / threat wording
# --------------------------------------------------------------------------- #

_FORBIDDEN = (
    "violation",
    "breach",
    "trespass",
    "illegal",
    "unauthorized",
    "incursion",
    "prohibited",
    "dangerous",
    "suspicious",
    "threat",
    "hostile",
    "abnormal",
    "military",
)


def _all_strings(obj) -> list[str]:
    out: list[str] = []
    if isinstance(obj, dict):
        for v in obj.values():
            out.extend(_all_strings(v))
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            out.extend(_all_strings(v))
    elif isinstance(obj, str):
        out.append(obj)
    return out


def test_no_forbidden_wording_in_any_result() -> None:
    results = [
        resolve_geographic_context(*KAOHSIUNG_IN_ANCHORAGE).to_dict(),
        resolve_geographic_context(*STRAIT_OPEN_WATER).to_dict(),
        resolve_geographic_context(*OUT_OF_COVERAGE).to_dict(),
    ]
    for result in results:
        blob = " ".join(_all_strings(result)).lower()
        for term in _FORBIDDEN:
            assert term not in blob, f"forbidden term {term!r} in GIS context output"


# --------------------------------------------------------------------------- #
# Endpoint
# --------------------------------------------------------------------------- #


def test_endpoint_returns_context_in_coverage(client) -> None:
    lon, lat = KAOHSIUNG_IN_ANCHORAGE
    resp = client.get(f"/context/geographic?lon={lon}&lat={lat}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["schema_version"] == SCHEMA_VERSION
    assert body["coverage"]["value"] == "in_coverage"
    assert body["nearest_port"]["value"]["id"] == "kaohsiung"
    assert body["distance_to_coast_km"]["provenance"] == "derived"
    assert body["named_areas_computed"] is True
    assert any(a["id"] == "kaohsiung-anchorage-a" for a in body["within_named_areas"])


def test_endpoint_out_of_coverage_is_unknown(client) -> None:
    resp = client.get("/context/geographic?lon=140&lat=10")
    assert resp.status_code == 200
    body = resp.json()
    assert body["coverage"]["provenance"] == "unknown"
    assert body["nearest_port"]["value"] is None
    assert body["named_areas_computed"] is False


def test_endpoint_rejects_out_of_range_coordinates(client) -> None:
    resp = client.get("/context/geographic?lon=999&lat=10")
    assert resp.status_code == 422


def test_endpoint_requires_both_coordinates(client) -> None:
    resp = client.get("/context/geographic?lon=120.3")
    assert resp.status_code == 422
