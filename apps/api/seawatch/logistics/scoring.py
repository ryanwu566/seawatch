"""Deterministic scoring with an exposed decomposition (design §8).

Pure arithmetic, stdlib only. Every candidate's score is decomposed into four
named terms so the Decision Brief can show *why* one port beat another:

    time_score     = w_time     * norm(eta_hours)
    cost_score     = w_cost     * norm(per_unit_cost + base_handling_cost)
    risk_score     = w_risk     * route_risk            # already in [0,1]
    capacity_score = w_capacity * capacity_penalty       # [0,1]
    total_score    = time_score + cost_score + risk_score + capacity_score

Priority is expressed by **allocation ordering**, never folded into the score.
``total_score`` is a planning preference ordering for this scenario only: it is
NOT a probability, threat level, legality judgement, or claim of real-world
operational superiority.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import Demand, Port, Route

DEFAULT_WEIGHTS = {"time": 0.35, "cost": 0.25, "risk": 0.20, "capacity": 0.20}


@dataclass(frozen=True)
class Weights:
    time: float
    cost: float
    risk: float
    capacity: float

    def as_dict(self) -> dict[str, float]:
        return {
            "time": self.time,
            "cost": self.cost,
            "risk": self.risk,
            "capacity": self.capacity,
        }


@dataclass(frozen=True)
class NormalizationBasis:
    """The min/max used to normalize each raw term across the candidate set."""

    eta_min: float
    eta_max: float
    cost_min: float
    cost_max: float


@dataclass(frozen=True)
class ScoreBreakdown:
    route_id: str
    port_id: str
    time_score: float
    cost_score: float
    risk_score: float
    capacity_score: float
    priority_effect: int
    total_score: float


class ScoringError(ValueError):
    """Raised for invalid weights."""


def normalize(values: list[float]) -> list[float]:
    """Min–max normalize to [0,1]. If all values are equal, return zeros.

    An empty input returns an empty list. This keeps terms comparable so raw
    units never dominate the score.
    """

    if not values:
        return []
    lo = min(values)
    hi = max(values)
    if hi == lo:
        return [0.0 for _ in values]
    span = hi - lo
    return [(v - lo) / span for v in values]


def normalize_weights(weights: dict[str, float] | None) -> Weights:
    """Validate and normalize weights to sum to 1.

    Negative or non-numeric weights raise :class:`ScoringError`. A missing key
    falls back to the default. A zero-sum (all zero) raises as degenerate.
    """

    raw = dict(DEFAULT_WEIGHTS)
    if weights:
        for key, value in weights.items():
            if key not in DEFAULT_WEIGHTS:
                raise ScoringError(f"unknown weight key: {key!r}")
            try:
                numeric = float(value)
            except (TypeError, ValueError) as exc:
                raise ScoringError(f"weight {key!r} is not numeric: {value!r}") from exc
            if numeric < 0:
                raise ScoringError(f"weight {key!r} must be non-negative")
            raw[key] = numeric
    total = sum(raw.values())
    if total <= 0:
        raise ScoringError("weights must have a positive sum")
    return Weights(
        time=raw["time"] / total,
        cost=raw["cost"] / total,
        risk=raw["risk"] / total,
        capacity=raw["capacity"] / total,
    )


def capacity_penalty(remaining_capacity: float, required_units: float) -> float:
    """Penalty in [0,1] rising as remaining capacity falls below the demand.

    - 0.0 when the port can fully absorb the demand (remaining >= required);
    - rises toward 1.0 as remaining shrinks relative to required;
    - 1.0 (hard exclusion signal) when no capacity remains.
    """

    if remaining_capacity <= 0:
        return 1.0
    if required_units <= 0:
        return 0.0
    if remaining_capacity >= required_units:
        return 0.0
    return 1.0 - (remaining_capacity / required_units)


def build_basis(routes: list[Route], ports: dict[str, Port]) -> NormalizationBasis:
    """Compute the min/max normalization basis for a candidate set."""

    etas = [r.baseline_eta_hours for r in routes]
    costs = [r.per_unit_cost + ports[r.from_port].base_handling_cost for r in routes]
    return NormalizationBasis(
        eta_min=min(etas) if etas else 0.0,
        eta_max=max(etas) if etas else 0.0,
        cost_min=min(costs) if costs else 0.0,
        cost_max=max(costs) if costs else 0.0,
    )


def _norm_one(value: float, lo: float, hi: float) -> float:
    if hi == lo:
        return 0.0
    return (value - lo) / (hi - lo)


def score_candidate(
    demand: Demand,
    route: Route,
    port: Port,
    weights: Weights,
    basis: NormalizationBasis,
    remaining_capacity: float,
) -> ScoreBreakdown:
    """Score a single candidate route/port for a demand (lower total = better)."""

    eta_term = _norm_one(route.baseline_eta_hours, basis.eta_min, basis.eta_max)
    cost_raw = route.per_unit_cost + port.base_handling_cost
    cost_term = _norm_one(cost_raw, basis.cost_min, basis.cost_max)
    risk_term = route.route_risk
    cap_term = capacity_penalty(remaining_capacity, demand.quantity_units)

    time_score = weights.time * eta_term
    cost_score = weights.cost * cost_term
    risk_score = weights.risk * risk_term
    capacity_score = weights.capacity * cap_term
    total = time_score + cost_score + risk_score + capacity_score

    return ScoreBreakdown(
        route_id=route.id,
        port_id=port.id,
        time_score=time_score,
        cost_score=cost_score,
        risk_score=risk_score,
        capacity_score=capacity_score,
        priority_effect=demand.priority,
        total_score=total,
    )
