"""Deterministic Decision Brief generator with provenance + language gates.

No LLM, no free prose: every text field is assembled from a fixed template
vocabulary and structured values, so output is byte-identical for identical
inputs and cannot drift into prohibited wording. The brief always carries a
``provenance_note`` and a ``provenance_summary`` whose counts equal the
dataset's contributing fields; provenance can never be erased or upgraded here.
"""

from __future__ import annotations

import re

from .dataset import Dataset
from .models import (
    Allocation,
    DecisionBrief,
    DisruptionScenario,
    Port,
)
from .provenance import summarize
from .scoring import Weights

# Shared forbidden-term list backing both the generator guard and the tests
# (design §1.3, hardening Language Hard Gate). Matched case-insensitively.
FORBIDDEN_TERMS: tuple[str, ...] = (
    "command",
    "dispatch immediately",
    "dispatch directive",
    "military recommendation",
    "military",
    "confirmed disruption",
    "real capacity",
    "verified inventory",
    "order",
    "tasking",
    "deploy",
    "deployment",
    "weapon",
    "troop",
    "strike",
    "attack",
    "enemy",
    "threat level",
)

PROVENANCE_NOTE_EN = (
    "Scenario-based planning estimates for human review; not real operational "
    "data and not a prediction of a real event."
)
PROVENANCE_NOTE_ZH = (
    "此為供人工審查的情境規劃估計值，並非真實作業資料，也非對真實事件的預測。"
)

SCHEMATIC_LABEL = "SCHEMATIC CONNECTOR / 示意連線"


class LanguageSafetyError(ValueError):
    """Raised when generated text contains a prohibited term."""


def assert_language_safe(text: str) -> None:
    """Raise if ``text`` contains any forbidden term (case-insensitive).

    Matching is on whole words / exact phrases (word boundaries) so benign
    substrings such as "ordering" or "border" do not trip the guard, while a
    standalone directive word like "order" still does.
    """

    lowered = text.lower()
    for term in FORBIDDEN_TERMS:
        pattern = r"\b" + re.escape(term) + r"\b"
        if re.search(pattern, lowered):
            raise LanguageSafetyError(f"prohibited term in generated text: {term!r}")


def _port_label(port: Port | None, port_id: str) -> str:
    if port is None:
        return port_id
    return f"{port.name_zh} {port.name_en}"


def _build_alternatives(
    scenario: DisruptionScenario,
    dataset: Dataset,
    allocations: list[Allocation],
) -> tuple[dict, ...]:
    """Per-port comparison rows from structured values (never parsed prose)."""

    used: dict[str, float] = {}
    for alloc in allocations:
        for assignment in alloc.assignments:
            used[assignment.port_id] = used.get(assignment.port_id, 0.0) + assignment.units

    rows: list[dict] = []
    routes = dataset.candidate_routes(scenario)
    seen_ports: list[str] = []
    for route in routes:
        if route.from_port in seen_ports:
            continue
        seen_ports.append(route.from_port)
        port = dataset.port(route.from_port)
        capacity = dataset.effective_capacity(scenario, route.from_port)
        utilization = (used.get(route.from_port, 0.0) / capacity) if capacity > 0 else 0.0
        rows.append(
            {
                "port_id": route.from_port,
                "port_label": _port_label(port, route.from_port),
                "eta_hours": route.baseline_eta_hours,
                "distance_km": route.distance_km,
                "per_unit_cost": round(route.per_unit_cost + (port.base_handling_cost if port else 0.0), 4),
                "capacity_units": capacity,
                "capacity_utilization": round(utilization, 4),
                "risk": route.route_risk,
                "schematic": route.schematic,
                "schematic_label": SCHEMATIC_LABEL if route.schematic else None,
                "route_source_type": route.source_type.value,
            }
        )
    return tuple(rows)


def _build_trade_offs(
    dataset: Dataset,
    allocations: list[Allocation],
) -> tuple[str, ...]:
    """Structured, template-based trade-off strings (decision-support language)."""

    trade_offs: list[str] = []
    demands_by_id = {d.id: d for d in dataset.demands}
    for alloc in allocations:
        demand = demands_by_id.get(alloc.demand_id)
        label = demand.commodity.value if demand else alloc.demand_id
        if len(alloc.assignments) > 1:
            ports = ", ".join(a.port_id for a in alloc.assignments)
            trade_offs.append(
                f"{label}: split across {ports} because no single alternative port had "
                f"enough remaining capacity; this is a planning estimate for human review."
            )
        if alloc.unmet_units > 0:
            trade_offs.append(
                f"{label}: {alloc.unmet_units:g} unit(s) could not be satisfied within the "
                f"scenario dataset; shown as unmet demand for human review."
            )
    if not trade_offs:
        trade_offs.append(
            "All affected demand satisfied within the scenario dataset; figures are "
            "planning estimates for human review."
        )
    return tuple(trade_offs)


def _build_summaries(
    scenario: DisruptionScenario,
    dataset: Dataset,
    allocations: list[Allocation],
) -> tuple[str, str]:
    satisfied = sum(a.satisfied_units for a in allocations)
    unmet = sum(a.unmet_units for a in allocations)
    demands_by_id = {d.id: d for d in dataset.demands}
    # Highest-priority demand first (allocations are already priority-ordered).
    lead = allocations[0] if allocations else None
    lead_label = ""
    lead_port = ""
    if lead and lead.assignments:
        demand = demands_by_id.get(lead.demand_id)
        lead_label = demand.commodity.value if demand else lead.demand_id
        lead_port = lead.assignments[0].port_id

    en = (
        f"Recommended allocation for the {scenario.name_en} scenario: "
        f"{satisfied:g} unit(s) routed to alternative civilian ports, "
        f"{unmet:g} unit(s) unmet. "
    )
    if lead_label and lead_port:
        en += (
            f"Highest-priority {lead_label} demand is prioritized via {lead_port}. "
        )
    en += "These are planning estimates for human review, not an instruction."

    zh = (
        f"{scenario.name_zh}的建議配置："
        f"共 {satisfied:g} 單位改由替代民用港口承接，{unmet:g} 單位未能滿足。"
    )
    if lead_label and lead_port:
        zh += f"最高優先的 {lead_label} 需求優先經由 {lead_port}。"
    zh += "以上為供人工審查的規劃估計值，並非指示。"
    return zh, en


def _build_unmet(dataset: Dataset, allocations: list[Allocation]) -> tuple[dict, ...]:
    demands_by_id = {d.id: d for d in dataset.demands}
    rows: list[dict] = []
    for alloc in allocations:
        if alloc.unmet_units > 0:
            demand = demands_by_id.get(alloc.demand_id)
            rows.append(
                {
                    "demand_id": alloc.demand_id,
                    "commodity": demand.commodity.value if demand else None,
                    "unmet_units": alloc.unmet_units,
                }
            )
    return tuple(rows)


def _contributing_records(scenario: DisruptionScenario, dataset: Dataset) -> list[object]:
    """All dataset records that contribute to this scenario's brief."""

    records: list[object] = list(dataset.ports)
    records += list(dataset.demands_for(scenario))
    records += list(dataset.candidate_routes(scenario))
    records += list(dataset.supplies)
    records.append(scenario)
    return records


def build_brief(
    scenario: DisruptionScenario,
    allocations: list[Allocation],
    dataset: Dataset,
    weights: Weights,
) -> DecisionBrief:
    """Assemble a deterministic, language-safe, provenance-carrying brief."""

    alternatives = _build_alternatives(scenario, dataset, allocations)
    trade_offs = _build_trade_offs(dataset, allocations)
    summary_zh, summary_en = _build_summaries(scenario, dataset, allocations)
    unmet_demand = _build_unmet(dataset, allocations)
    provenance_summary = summarize(_contributing_records(scenario, dataset))

    assumptions = (
        f"Weights: time {weights.time:.2f} / cost {weights.cost:.2f} / "
        f"risk {weights.risk:.2f} / capacity {weights.capacity:.2f} (normalized to sum 1).",
        "Capacity is abstract planning units/day (synthetic), never real port throughput.",
        "ETA, cost and risk are scenario/synthetic planning indices for human review.",
        "Distances are derived great-circle values between public civilian coordinates.",
        f"Priority ordering: lower priority number allocated first ({', '.join(a.demand_id for a in allocations)}).",
    )

    provenance_note = f"{PROVENANCE_NOTE_ZH} {PROVENANCE_NOTE_EN}"

    # Language gate on every generated text field.
    for text in (summary_zh, summary_en, provenance_note, *trade_offs, *assumptions):
        assert_language_safe(text)

    return DecisionBrief(
        scenario_id=scenario.id,
        summary_zh=summary_zh,
        summary_en=summary_en,
        recommended_allocations=tuple(allocations),
        alternatives=alternatives,
        trade_offs=trade_offs,
        unmet_demand=unmet_demand,
        provenance_note=provenance_note,
        assumptions=assumptions,
        provenance_summary=provenance_summary,
    )
