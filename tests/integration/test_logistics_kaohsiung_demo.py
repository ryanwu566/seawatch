"""Slice K — deterministic Kaohsiung disruption demo: golden end-to-end lock.

This integration test locks the SENSE → SURVIVE → RESPOND demonstration's
RESPOND result to exact, hand-reviewed values computed by the real engine
(dataset + scoring + priority-ordered, capacity-aware, split allocation +
Decision Brief). It proves the demo is:

  * deterministic (same input ⇒ byte-identical output),
  * free of randomness / external APIs / LLM / DB / live-AIS dependency
    (the pure simulate opens no outbound socket),
  * provenance-preserving (summary counts exact; scenario/synthetic never
    upgraded; derived names its method),
  * language-safe (no prohibited autonomous-command wording),
  * medical-first with the expected split.

No production code is added by this slice; it only verifies prior slices.
"""

from __future__ import annotations

import socket

import pytest
from fastapi.testclient import TestClient

from apps.api.seawatch.logistics.brief import FORBIDDEN_TERMS, assert_language_safe
from apps.api.seawatch.main import create_app

SCENARIO_ID = "kaohsiung-disruption"


@pytest.fixture()
def client():
    with TestClient(create_app()) as c:
        yield c


def _simulate(client) -> dict:
    resp = client.post("/logistics/simulate", json={"scenario_id": SCENARIO_ID})
    assert resp.status_code == 200
    return resp.json()


def _alloc(body: dict, demand_id: str) -> dict:
    matches = [a for a in body["recommended_allocations"] if a["demand_id"] == demand_id]
    assert len(matches) == 1, f"expected exactly one allocation for {demand_id}"
    return matches[0]


# --------------------------------------------------------------------------- #
# 1. Demo scenario produces the EXPECTED allocations (golden lock).
# --------------------------------------------------------------------------- #


def test_demo_scenario_disrupts_kaohsiung_only(client) -> None:
    ctx = client.get(f"/logistics/scenarios/{SCENARIO_ID}")
    assert ctx.status_code == 200
    body = ctx.json()
    assert body["scenario"]["disrupted_ports"] == ["kaohsiung"]
    # Kaohsiung is excluded from the candidate (alternative) ports.
    assert "kaohsiung" not in body["candidate_ports"]
    assert set(body["candidate_ports"]) == {"taichung", "keelung"}


def test_demo_medical_allocated_first_to_taichung(client) -> None:
    body = _simulate(client)
    # Medical is highest priority and must be the FIRST allocation processed.
    assert body["recommended_allocations"][0]["demand_id"] == "medical-south"
    medical = _alloc(body, "medical-south")
    assert medical["satisfied_units"] == 30.0
    assert medical["unmet_units"] == 0.0
    assert len(medical["assignments"]) == 1
    asg = medical["assignments"][0]
    assert asg["port_id"] == "taichung"
    assert asg["route_id"] == "taichung->south-node"
    assert asg["units"] == 30.0
    assert asg["eta_hours"] == 9.5
    assert asg["cost"] == 2.2
    assert asg["risk"] == 0.21


def test_demo_food_is_split_taichung_then_keelung(client) -> None:
    body = _simulate(client)
    food = _alloc(body, "food-south")
    assert food["satisfied_units"] == 50.0
    assert food["unmet_units"] == 0.0
    # Deterministic split: fill best-scoring feasible port (taichung) to its
    # remaining capacity (30 left after medical), then keelung for the rest.
    assert [a["port_id"] for a in food["assignments"]] == ["taichung", "keelung"]
    taichung, keelung = food["assignments"]
    assert taichung["units"] == 30.0
    assert taichung["eta_hours"] == 9.5
    assert keelung["units"] == 20.0
    assert keelung["port_id"] == "keelung"
    assert keelung["eta_hours"] == 15.0


def test_demo_fuel_allocated_to_keelung(client) -> None:
    body = _simulate(client)
    fuel = _alloc(body, "fuel-south")
    assert fuel["satisfied_units"] == 40.0
    assert fuel["unmet_units"] == 0.0
    assert len(fuel["assignments"]) == 1
    asg = fuel["assignments"][0]
    assert asg["port_id"] == "keelung"
    assert asg["units"] == 40.0
    assert asg["eta_hours"] == 15.0


def test_demo_total_routed_120_zero_unmet(client) -> None:
    body = _simulate(client)
    total_satisfied = sum(a["satisfied_units"] for a in body["recommended_allocations"])
    total_unmet = sum(a["unmet_units"] for a in body["recommended_allocations"])
    assert total_satisfied == 120.0
    assert total_unmet == 0.0
    assert body["unmet_demand"] == []


def test_demo_alternatives_metrics_are_exact(client) -> None:
    body = _simulate(client)
    alts = {a["port_id"]: a for a in body["alternatives"]}
    assert set(alts) == {"taichung", "keelung"}

    taichung = alts["taichung"]
    assert taichung["eta_hours"] == 9.5
    assert taichung["distance_km"] == 185.8
    assert taichung["per_unit_cost"] == 2.2
    assert taichung["capacity_units"] == 60.0
    assert taichung["capacity_utilization"] == 1.0  # 60/60 used
    assert taichung["risk"] == 0.21
    assert taichung["schematic"] is True
    assert taichung["schematic_label"] == "SCHEMATIC CONNECTOR / 示意連線"
    assert taichung["route_source_type"] == "derived"

    keelung = alts["keelung"]
    assert keelung["eta_hours"] == 15.0
    assert keelung["distance_km"] == 314.7
    assert keelung["per_unit_cost"] == 2.6
    assert keelung["capacity_units"] == 70.0
    assert keelung["capacity_utilization"] == 0.8571  # 60/70 used, rounded(4)
    assert keelung["risk"] == 0.28
    assert keelung["schematic"] is True
    assert keelung["route_source_type"] == "derived"


def test_demo_trade_offs_report_the_food_split(client) -> None:
    body = _simulate(client)
    assert len(body["trade_offs"]) == 1
    text = body["trade_offs"][0]
    assert text.startswith("food: split across taichung, keelung")
    assert "planning estimate for human review" in text


# --------------------------------------------------------------------------- #
# 2. Same input produces identical output (determinism, no randomness).
# --------------------------------------------------------------------------- #


def test_demo_is_byte_identical_across_runs(client) -> None:
    first = _simulate(client)
    second = _simulate(client)
    third = _simulate(client)
    assert first == second == third


def test_demo_is_identical_across_fresh_app_instances(client) -> None:
    """A fresh app/engine must reproduce the exact same brief (no hidden state)."""
    body_a = _simulate(client)
    with TestClient(create_app()) as other:
        body_b = other.post(
            "/logistics/simulate", json={"scenario_id": SCENARIO_ID}
        ).json()
    assert body_a == body_b


# --------------------------------------------------------------------------- #
# 3. Provenance / truth labels remain (never erased or upgraded).
# --------------------------------------------------------------------------- #


def test_demo_provenance_summary_counts_are_exact(client) -> None:
    body = _simulate(client)
    assert body["provenance_summary"] == {
        "official": 3,
        "derived": 2,
        "scenario": 7,
        "synthetic": 0,
    }


def test_demo_provenance_note_present_and_truthful(client) -> None:
    body = _simulate(client)
    note = body["provenance_note"]
    assert "human review" in note
    assert "not real operational data" in note
    assert "not a prediction" in note


def test_demo_scenario_and_derived_classes_not_upgraded(client) -> None:
    body = _simulate(client)
    # Alternatives' route provenance stays derived (great-circle), never official.
    for alt in body["alternatives"]:
        assert alt["route_source_type"] == "derived"
    # Assumptions explicitly keep capacity synthetic and ETA/cost/risk scenario.
    joined = " ".join(body["assumptions"])
    assert "synthetic" in joined
    assert "derived great-circle" in joined


# --------------------------------------------------------------------------- #
# 4. No prohibited autonomous-command wording anywhere in the generated output.
# --------------------------------------------------------------------------- #


def test_demo_output_contains_no_prohibited_wording(client) -> None:
    body = _simulate(client)
    text_fields = [
        body["summary_zh"],
        body["summary_en"],
        body["provenance_note"],
        *body["trade_offs"],
        *body["assumptions"],
    ]
    for text in text_fields:
        # Does not raise.
        assert_language_safe(text)

    blob = " ".join(text_fields).lower()
    for term in FORBIDDEN_TERMS:
        assert f" {term} " not in f" {blob} ", f"prohibited term leaked: {term!r}"


# --------------------------------------------------------------------------- #
# 5. Pure demo: no external APIs / LLM / DB / live-AIS dependency.
# --------------------------------------------------------------------------- #


def test_demo_simulation_opens_no_outbound_socket(client, monkeypatch) -> None:
    original_connect = socket.socket.connect

    def _blocked(self, address):  # noqa: ANN001
        raise AssertionError(f"demo simulate opened an outbound socket to {address!r}")

    monkeypatch.setattr(socket.socket, "connect", _blocked)
    try:
        resp = client.post("/logistics/simulate", json={"scenario_id": SCENARIO_ID})
    finally:
        monkeypatch.setattr(socket.socket, "connect", original_connect)
    assert resp.status_code == 200


def test_demo_does_not_depend_on_live_ais(client) -> None:
    """The RESPOND result is identical regardless of live/resilience state."""
    baseline = _simulate(client)
    # Touch the Phase 8 read-only endpoints; the demo result must not change.
    client.get("/live/health")
    client.get("/resilience/status")
    assert _simulate(client) == baseline
