"""Slice C — deterministic scoring engine tests."""

from __future__ import annotations

import pytest

from apps.api.seawatch.logistics.models import (
    Commodity,
    Demand,
    Port,
    Route,
    SourceMetadata,
    SourceType,
)
from apps.api.seawatch.logistics.scoring import (
    DEFAULT_WEIGHTS,
    NormalizationBasis,
    ScoringError,
    Weights,
    build_basis,
    capacity_penalty,
    normalize,
    normalize_weights,
    score_candidate,
)


def _port(pid: str, cost: float) -> Port:
    return Port(
        id=pid,
        name_zh=pid,
        name_en=pid,
        lon=120.5,
        lat=24.0,
        capacity_units=100.0,
        base_handling_cost=cost,
        source_type=SourceType.SCENARIO,
    )


def _route(rid: str, port: str, eta: float, cost: float, risk: float) -> Route:
    return Route(
        id=rid,
        from_port=port,
        to_demand_node="south-node",
        distance_km=100.0,
        baseline_eta_hours=eta,
        per_unit_cost=cost,
        route_risk=risk,
        source_type=SourceType.DERIVED,
        schematic=True,
        source_metadata=SourceMetadata(derivation_method="great-circle"),
    )


def _demand(qty: float = 30.0, priority: int = 1) -> Demand:
    return Demand(
        id="medical-south",
        commodity=Commodity.MEDICAL,
        priority=priority,
        quantity_units=qty,
        origin_demand_node="south-node",
        normally_served_by="kaohsiung",
        source_type=SourceType.SCENARIO,
    )


def test_normalize_basic() -> None:
    assert normalize([0.0, 5.0, 10.0]) == [0.0, 0.5, 1.0]


def test_normalize_single_value_is_zero() -> None:
    assert normalize([7.0]) == [0.0]


def test_normalize_all_equal_is_zeros() -> None:
    assert normalize([3.0, 3.0, 3.0]) == [0.0, 0.0, 0.0]


def test_normalize_empty() -> None:
    assert normalize([]) == []


def test_normalize_weights_sum_to_one() -> None:
    w = normalize_weights(None)
    assert w.time + w.cost + w.risk + w.capacity == pytest.approx(1.0)
    # defaults already sum to 1
    assert w.time == pytest.approx(0.35)
    assert w.cost == pytest.approx(0.25)


def test_normalize_weights_rescales() -> None:
    w = normalize_weights({"time": 1, "cost": 1, "risk": 1, "capacity": 1})
    assert w.time == pytest.approx(0.25)
    assert w.time + w.cost + w.risk + w.capacity == pytest.approx(1.0)


def test_normalize_weights_rejects_negative() -> None:
    with pytest.raises(ScoringError):
        normalize_weights({"time": -0.5})


def test_normalize_weights_rejects_non_numeric() -> None:
    with pytest.raises(ScoringError):
        normalize_weights({"time": "fast"})


def test_normalize_weights_rejects_unknown_key() -> None:
    with pytest.raises(ScoringError):
        normalize_weights({"speed": 1.0})


def test_normalize_weights_rejects_zero_sum() -> None:
    with pytest.raises(ScoringError):
        normalize_weights({"time": 0, "cost": 0, "risk": 0, "capacity": 0})


def test_capacity_penalty_curve() -> None:
    assert capacity_penalty(100.0, 30.0) == 0.0  # ample
    assert capacity_penalty(0.0, 30.0) == 1.0  # exhausted
    assert capacity_penalty(15.0, 30.0) == pytest.approx(0.5)  # half short


def test_golden_score_decomposition() -> None:
    # Two candidates. Taichung: eta 9.5, cost 1.2+1.0=2.2, risk 0.21.
    # Keelung:  eta 15.0, cost 1.45+1.15=2.6, risk 0.28.
    taichung = _port("taichung", 1.0)
    keelung = _port("keelung", 1.15)
    r_tai = _route("taichung->south-node", "taichung", 9.5, 1.2, 0.21)
    r_kee = _route("keelung->south-node", "keelung", 15.0, 1.45, 0.28)
    ports = {"taichung": taichung, "keelung": keelung}
    routes = [r_tai, r_kee]
    basis = build_basis(routes, ports)
    weights = normalize_weights(None)
    demand = _demand(qty=30.0)

    # Normalization basis derived from the formula, not magic numbers.
    assert basis.eta_min == 9.5
    assert basis.eta_max == 15.0
    assert basis.cost_min == pytest.approx(2.2)
    assert basis.cost_max == pytest.approx(2.6)

    bt = score_candidate(demand, r_tai, taichung, weights, basis, remaining_capacity=60.0)
    bk = score_candidate(demand, r_kee, keelung, weights, basis, remaining_capacity=70.0)

    # Taichung is the min on eta and cost => normalized terms 0.0; risk only.
    exp_tai_time = 0.35 * 0.0
    exp_tai_cost = 0.25 * 0.0
    exp_tai_risk = 0.20 * 0.21
    exp_tai_cap = 0.20 * 0.0
    assert bt.time_score == pytest.approx(exp_tai_time)
    assert bt.cost_score == pytest.approx(exp_tai_cost)
    assert bt.risk_score == pytest.approx(exp_tai_risk)
    assert bt.capacity_score == pytest.approx(exp_tai_cap)
    assert bt.total_score == pytest.approx(
        exp_tai_time + exp_tai_cost + exp_tai_risk + exp_tai_cap
    )

    # Keelung is the max on eta (norm 1.0) and cost (norm 1.0).
    exp_kee_time = 0.35 * 1.0
    exp_kee_cost = 0.25 * 1.0
    exp_kee_risk = 0.20 * 0.28
    exp_kee_cap = 0.20 * 0.0
    assert bk.total_score == pytest.approx(
        exp_kee_time + exp_kee_cost + exp_kee_risk + exp_kee_cap
    )
    # Taichung must be preferred (lower total).
    assert bt.total_score < bk.total_score


def test_total_excludes_priority_effect() -> None:
    port = _port("taichung", 1.0)
    route = _route("r", "taichung", 9.5, 1.2, 0.21)
    basis = NormalizationBasis(9.5, 9.5, 2.2, 2.2)
    weights = normalize_weights(None)
    b = score_candidate(_demand(priority=1), route, port, weights, basis, 60.0)
    manual = b.time_score + b.cost_score + b.risk_score + b.capacity_score
    assert b.total_score == pytest.approx(manual)
    assert b.priority_effect == 1  # recorded, not summed


def test_defaults_constant_sums_to_one() -> None:
    assert sum(DEFAULT_WEIGHTS.values()) == pytest.approx(1.0)
