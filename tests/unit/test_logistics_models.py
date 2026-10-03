"""Slice A — domain contract tests for the logistics module."""

from __future__ import annotations

import dataclasses

import pytest

from apps.api.seawatch.logistics.models import (
    Allocation,
    Assignment,
    Commodity,
    DecisionBrief,
    Demand,
    DisruptionScenario,
    Port,
    Route,
    SourceMetadata,
    SourceType,
    Supply,
)


def test_source_type_wire_values_are_stable() -> None:
    assert [s.value for s in SourceType] == [
        "official",
        "derived",
        "scenario",
        "synthetic",
    ]


def test_source_type_rejects_unknown_value() -> None:
    with pytest.raises(ValueError):
        SourceType("made_up")


def test_commodity_wire_values_are_stable() -> None:
    assert [c.value for c in Commodity] == ["medical", "food", "fuel"]


def test_port_round_trips_fields() -> None:
    port = Port(
        id="taichung",
        name_zh="臺中港",
        name_en="Taichung",
        lon=120.52,
        lat=24.29,
        capacity_units=120.0,
        base_handling_cost=1.0,
        source_type=SourceType.SCENARIO,
    )
    assert port.id == "taichung"
    assert port.lon == pytest.approx(120.52)
    assert port.source_type is SourceType.SCENARIO


def test_demand_and_supply_and_route_round_trip() -> None:
    demand = Demand(
        id="medical-south",
        commodity=Commodity.MEDICAL,
        priority=1,
        quantity_units=40.0,
        origin_demand_node="south-node",
        normally_served_by="kaohsiung",
        source_type=SourceType.SCENARIO,
    )
    supply = Supply(
        id="medical-supply",
        commodity=Commodity.MEDICAL,
        available_units=100.0,
        entry_port_options=("taichung", "keelung"),
        source_type=SourceType.SCENARIO,
    )
    route = Route(
        id="taichung->south-node",
        from_port="taichung",
        to_demand_node="south-node",
        distance_km=180.0,
        baseline_eta_hours=9.5,
        per_unit_cost=1.2,
        route_risk=0.21,
        source_type=SourceType.DERIVED,
        source_metadata=SourceMetadata(derivation_method="great-circle"),
    )
    assert demand.commodity is Commodity.MEDICAL
    assert supply.entry_port_options == ("taichung", "keelung")
    assert route.route_risk == pytest.approx(0.21)
    assert route.schematic is False


def test_records_are_frozen_no_provenance_mutation() -> None:
    port = Port(
        id="keelung",
        name_zh="基隆港",
        name_en="Keelung",
        lon=121.74,
        lat=25.14,
        capacity_units=80.0,
        base_handling_cost=1.1,
        source_type=SourceType.SCENARIO,
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        port.source_type = SourceType.OFFICIAL  # type: ignore[misc]


def test_allocation_and_brief_round_trip() -> None:
    assignment = Assignment(
        port_id="taichung",
        route_id="taichung->south-node",
        units=40.0,
        eta_hours=9.5,
        cost=1.2,
        risk=0.21,
    )
    allocation = Allocation(
        demand_id="medical-south",
        assignments=(assignment,),
        satisfied_units=40.0,
        unmet_units=0.0,
        score=0.33,
    )
    brief = DecisionBrief(
        scenario_id="kaohsiung-disruption",
        summary_zh="摘要",
        summary_en="summary",
        recommended_allocations=(allocation,),
        alternatives=(),
        trade_offs=(),
        unmet_demand=(),
        provenance_note="scenario-based planning estimates for human review",
        assumptions=(),
        provenance_summary={"official": 0, "derived": 0, "scenario": 0, "synthetic": 0},
    )
    assert brief.recommended_allocations[0].assignments[0].port_id == "taichung"
    assert brief.recommended_allocations[0].satisfied_units == pytest.approx(40.0)


def test_disruption_scenario_defaults_capacity_overrides_empty() -> None:
    scenario = DisruptionScenario(
        id="kaohsiung-disruption",
        name_zh="高雄港中斷情境",
        name_en="Kaohsiung Port Disruption",
        disrupted_ports=("kaohsiung",),
        description_zh="情境",
        description_en="scenario",
        source_type=SourceType.SCENARIO,
    )
    assert scenario.capacity_overrides == {}
    assert scenario.disrupted_ports == ("kaohsiung",)
