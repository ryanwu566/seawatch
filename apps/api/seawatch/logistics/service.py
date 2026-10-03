"""Compose dataset + scoring + optimizer + brief into a pure simulate call.

``simulate`` is **pure**: same ``scenario_id`` + ``weights`` + dataset ⇒
byte-identical :class:`DecisionBrief`. It opens no socket, reads no live store,
calls no provider/DB/LLM, and persists nothing. The only I/O is reading the
curated dataset file once at module import (and never per request).
"""

from __future__ import annotations

from .brief import build_brief
from .dataset import Dataset, DatasetError, load
from .models import DecisionBrief
from .optimizer import allocate
from .scoring import normalize_weights


class ScenarioNotFoundError(KeyError):
    """Raised when a requested scenario id is not in the dataset."""


def _load_dataset_safely() -> Dataset | None:
    """Load the dataset once; return None (not raise) on failure so the API can
    start with an empty scenario list and log one actionable error."""

    try:
        return load()
    except DatasetError:
        return None


# Loaded once at import. A load failure yields an empty, still-functional module.
_DATASET: Dataset | None = _load_dataset_safely()


def get_dataset() -> Dataset | None:
    return _DATASET


def list_scenarios() -> list[dict]:
    if _DATASET is None:
        return []
    return [
        {
            "id": s.id,
            "name_zh": s.name_zh,
            "name_en": s.name_en,
            "disrupted_ports": list(s.disrupted_ports),
            "source_type": s.source_type.value,
        }
        for s in _DATASET.scenarios
    ]


def scenario_context(scenario_id: str) -> dict:
    if _DATASET is None:
        raise ScenarioNotFoundError(scenario_id)
    scenario = _DATASET.scenario(scenario_id)
    if scenario is None:
        raise ScenarioNotFoundError(scenario_id)
    demands = _DATASET.demands_for(scenario)
    routes = _DATASET.candidate_routes(scenario)
    from .provenance import summarize

    records: list[object] = list(_DATASET.ports)
    records += list(demands)
    records += list(routes)
    records += list(_DATASET.supplies)
    records.append(scenario)
    return {
        "scenario": {
            "id": scenario.id,
            "name_zh": scenario.name_zh,
            "name_en": scenario.name_en,
            "disrupted_ports": list(scenario.disrupted_ports),
            "description_zh": scenario.description_zh,
            "description_en": scenario.description_en,
            "source_type": scenario.source_type.value,
        },
        "affected_demands": [
            {
                "id": d.id,
                "commodity": d.commodity.value,
                "priority": d.priority,
                "quantity_units": d.quantity_units,
                "origin_demand_node": d.origin_demand_node,
                "source_type": d.source_type.value,
            }
            for d in demands
        ],
        "candidate_ports": sorted({r.from_port for r in routes}),
        "candidate_routes": [
            {
                "id": r.id,
                "from_port": r.from_port,
                "to_demand_node": r.to_demand_node,
                "distance_km": r.distance_km,
                "baseline_eta_hours": r.baseline_eta_hours,
                "route_risk": r.route_risk,
                "schematic": r.schematic,
                "source_type": r.source_type.value,
            }
            for r in routes
        ],
        "provenance_summary": summarize(records),
    }


def simulate(scenario_id: str, weights: dict[str, float] | None = None) -> DecisionBrief:
    """Pure read-and-compute: dataset + scenario + weights ⇒ DecisionBrief."""

    if _DATASET is None:
        raise ScenarioNotFoundError(scenario_id)
    scenario = _DATASET.scenario(scenario_id)
    if scenario is None:
        raise ScenarioNotFoundError(scenario_id)
    normalized = normalize_weights(weights)
    allocations = allocate(scenario, _DATASET, normalized)
    return build_brief(scenario, allocations, _DATASET, normalized)
