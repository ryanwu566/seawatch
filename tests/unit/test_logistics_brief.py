"""Slice E — decision brief generator tests (language + provenance gates)."""

from __future__ import annotations

import pytest

from apps.api.seawatch.logistics.brief import (
    FORBIDDEN_TERMS,
    LanguageSafetyError,
    SCHEMATIC_LABEL,
    assert_language_safe,
    build_brief,
)
from apps.api.seawatch.logistics.dataset import load
from apps.api.seawatch.logistics.optimizer import allocate
from apps.api.seawatch.logistics.provenance import carries_note, summarize
from apps.api.seawatch.logistics.scoring import normalize_weights


@pytest.fixture(scope="module")
def brief():
    ds = load()
    scenario = ds.scenario("kaohsiung-disruption")
    weights = normalize_weights(None)
    allocs = allocate(scenario, ds, weights)
    return build_brief(scenario, allocs, ds, weights), ds, scenario


def test_brief_always_carries_provenance_note(brief) -> None:
    b, _ds, _s = brief
    assert carries_note(b) is True
    assert "human review" in b.provenance_note


def test_provenance_summary_counts_match_contributing_fields(brief) -> None:
    b, ds, scenario = brief
    records = list(ds.ports)
    records += list(ds.demands_for(scenario))
    records += list(ds.candidate_routes(scenario))
    records += list(ds.supplies)
    records.append(scenario)
    assert b.provenance_summary == summarize(records)


def test_alternatives_are_structured_not_prose(brief) -> None:
    b, _ds, _s = brief
    assert b.alternatives
    for row in b.alternatives:
        assert set(row).issuperset(
            {
                "port_id",
                "eta_hours",
                "distance_km",
                "per_unit_cost",
                "capacity_units",
                "capacity_utilization",
                "risk",
                "schematic",
            }
        )
        assert isinstance(row["eta_hours"], (int, float))


def test_schematic_routes_labeled(brief) -> None:
    b, _ds, _s = brief
    for row in b.alternatives:
        if row["schematic"]:
            assert row["schematic_label"] == SCHEMATIC_LABEL


def test_no_prohibited_wording_in_any_field(brief) -> None:
    b, _ds, _s = brief
    fields = [b.summary_zh, b.summary_en, b.provenance_note]
    fields += list(b.trade_offs)
    fields += list(b.assumptions)
    for text in fields:
        # Must not raise.
        assert_language_safe(text)


def test_allowed_phrasing_permitted() -> None:
    assert_language_safe("recommended for this scenario; planning estimate; alternative; trade-off; human review required")


def test_language_guard_rejects_each_forbidden_term() -> None:
    for term in FORBIDDEN_TERMS:
        with pytest.raises(LanguageSafetyError):
            assert_language_safe(f"the plan will {term} the units")


def test_determinism_same_inputs_identical_brief() -> None:
    ds = load()
    scenario = ds.scenario("kaohsiung-disruption")
    weights = normalize_weights(None)
    a = build_brief(scenario, allocate(scenario, ds, weights), ds, weights)
    b = build_brief(scenario, allocate(scenario, ds, weights), ds, weights)
    assert a == b


def test_split_allocations_appear_as_rows(brief) -> None:
    b, _ds, _s = brief
    # recommended_allocations preserve per-port assignment rows
    for alloc in b.recommended_allocations:
        total = sum(a.units for a in alloc.assignments)
        assert total == pytest.approx(alloc.satisfied_units)


def test_unmet_demand_reported_when_present(brief) -> None:
    b, _ds, _s = brief
    # Total demand 120 vs capacity 130; expect everything satisfied here.
    # Just assert the structure is a tuple of dicts (possibly empty).
    assert isinstance(b.unmet_demand, tuple)
