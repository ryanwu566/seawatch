"""Priority-ordered, capacity-aware greedy allocation (design §7, §9).

This is the optimizer interface seam. ``GreedyPriorityOptimizer`` is the V1
implementation; a future phase could swap in LP/min-cost-flow behind the same
``Optimizer`` protocol without changing the API contract.

Behavior (all deterministic and individually testable):

- demands are processed in ascending ``priority`` (medical before food before
  fuel), ties broken by descending ``quantity`` then lexicographic ``id``;
- for each demand, feasible candidate routes (non-disrupted port, matching
  demand node, remaining port capacity > 0, remaining commodity supply > 0) are
  scored and sorted by ``total_score`` with the Scoring Contract tie-break;
- the best feasible port is filled up to its remaining capacity (and remaining
  commodity supply), then the next, until the demand is satisfied or no feasible
  capacity remains — i.e. **split allocation is allowed**;
- any residual is reported as ``unmet_units``; nothing is silently dropped.
"""

from __future__ import annotations

from typing import Protocol

from .dataset import Dataset
from .models import (
    Allocation,
    Assignment,
    Commodity,
    Demand,
    DisruptionScenario,
)
from .scoring import (
    ScoreBreakdown,
    Weights,
    build_basis,
    normalize_weights,
    score_candidate,
)


class Optimizer(Protocol):
    def allocate(
        self,
        scenario: DisruptionScenario,
        dataset: Dataset,
        weights: Weights,
    ) -> list[Allocation]:
        ...


def _demand_sort_key(demand: Demand) -> tuple[int, float, str]:
    # ascending priority, then descending quantity (negate), then id.
    return (demand.priority, -demand.quantity_units, demand.id)


def _tie_break_key(breakdown: ScoreBreakdown, eta: float, cost: float, risk: float):
    # total_score, then lower eta, lower combined cost, lower risk, then route id.
    return (breakdown.total_score, eta, cost, risk, breakdown.route_id)


class GreedyPriorityOptimizer:
    """Deterministic greedy allocator with split support."""

    def allocate(
        self,
        scenario: DisruptionScenario,
        dataset: Dataset,
        weights: Weights,
    ) -> list[Allocation]:
        ports_by_id = {p.id: p for p in dataset.ports}
        # Remaining port capacity ledger under this scenario.
        remaining_capacity: dict[str, float] = {
            p.id: dataset.effective_capacity(scenario, p.id) for p in dataset.ports
        }
        # Remaining commodity supply ledger.
        remaining_supply: dict[Commodity, float] = {}
        for supply in dataset.supplies:
            remaining_supply[supply.commodity] = (
                remaining_supply.get(supply.commodity, 0.0) + supply.available_units
            )
        # Ports that may receive a commodity (union of entry_port_options).
        supply_ports: dict[Commodity, set[str]] = {}
        for supply in dataset.supplies:
            supply_ports.setdefault(supply.commodity, set()).update(supply.entry_port_options)

        candidate_routes = dataset.candidate_routes(scenario)
        affected = sorted(dataset.demands_for(scenario), key=_demand_sort_key)

        allocations: list[Allocation] = []
        for demand in affected:
            allocations.append(
                self._allocate_one(
                    demand,
                    candidate_routes,
                    ports_by_id,
                    remaining_capacity,
                    remaining_supply,
                    supply_ports,
                    weights,
                )
            )
        return allocations

    def _allocate_one(
        self,
        demand: Demand,
        candidate_routes,
        ports_by_id,
        remaining_capacity: dict[str, float],
        remaining_supply: dict[Commodity, float],
        supply_ports: dict,
        weights: Weights,
    ) -> Allocation:
        # Eligible routes: serve this demand node, port exists, port can receive
        # this commodity (entry_port_options), and basis is computed over the
        # eligible set for honest normalization.
        allowed_ports = supply_ports.get(demand.commodity, set())
        eligible = [
            r
            for r in candidate_routes
            if r.to_demand_node == demand.origin_demand_node
            and r.from_port in ports_by_id
            and r.from_port in allowed_ports
        ]
        basis = build_basis(eligible, ports_by_id) if eligible else None

        assignments: list[Assignment] = []
        satisfied = 0.0
        remaining_need = demand.quantity_units
        best_total_score = 0.0

        while remaining_need > 1e-9 and eligible:
            # Score currently-feasible routes (port capacity + supply > 0).
            scored = []
            for route in eligible:
                port = ports_by_id[route.from_port]
                cap = remaining_capacity.get(route.from_port, 0.0)
                sup = remaining_supply.get(demand.commodity, 0.0)
                if cap <= 1e-9 or sup <= 1e-9:
                    continue
                breakdown = score_candidate(
                    demand, route, port, weights, basis, remaining_capacity=cap
                )
                combined_cost = route.per_unit_cost + port.base_handling_cost
                scored.append((breakdown, route, port, cap, sup, combined_cost))
            if not scored:
                break
            scored.sort(
                key=lambda item: _tie_break_key(
                    item[0], item[1].baseline_eta_hours, item[5], item[1].route_risk
                )
            )
            breakdown, route, port, cap, sup, _cost = scored[0]
            best_total_score = max(best_total_score, breakdown.total_score)

            take = min(remaining_need, cap, sup)
            if take <= 1e-9:
                break
            assignments.append(
                Assignment(
                    port_id=port.id,
                    route_id=route.id,
                    units=round(take, 6),
                    eta_hours=route.baseline_eta_hours,
                    cost=route.per_unit_cost + port.base_handling_cost,
                    risk=route.route_risk,
                )
            )
            remaining_capacity[route.from_port] = cap - take
            remaining_supply[demand.commodity] = sup - take
            satisfied += take
            remaining_need -= take

        unmet = max(0.0, demand.quantity_units - satisfied)
        return Allocation(
            demand_id=demand.id,
            assignments=tuple(assignments),
            satisfied_units=round(satisfied, 6),
            unmet_units=round(unmet, 6),
            score=round(best_total_score, 6),
        )


def allocate(
    scenario: DisruptionScenario,
    dataset: Dataset,
    weights: dict[str, float] | Weights | None = None,
) -> list[Allocation]:
    """Convenience entry point used by the service layer."""

    normalized = weights if isinstance(weights, Weights) else normalize_weights(weights)
    return GreedyPriorityOptimizer().allocate(scenario, dataset, normalized)
