"""Pydantic request/response schemas for the logistics API.

These live inside the logistics package (not ``apps/api/seawatch/schemas/``) to
keep Phase 9 fully self-contained. They mirror the domain dataclasses and the
Decision Brief, and provide a serializer from the frozen dataclass to the
response model.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from .models import DecisionBrief


class WeightsIn(BaseModel):
    time: float | None = Field(default=None, ge=0.0)
    cost: float | None = Field(default=None, ge=0.0)
    risk: float | None = Field(default=None, ge=0.0)
    capacity: float | None = Field(default=None, ge=0.0)

    def to_dict(self) -> dict[str, float] | None:
        provided = {k: v for k, v in self.model_dump().items() if v is not None}
        return provided or None


class SimulateRequest(BaseModel):
    scenario_id: str = Field(..., description="Disruption scenario id to evaluate.")
    weights: WeightsIn | None = Field(
        default=None,
        description="Optional objective weights; defaults applied and normalized to sum 1.",
    )


class ScenarioSummary(BaseModel):
    id: str
    name_zh: str
    name_en: str
    disrupted_ports: list[str]
    source_type: str


class ScenarioListResponse(BaseModel):
    count: int
    scenarios: list[ScenarioSummary]


class AssignmentOut(BaseModel):
    port_id: str
    route_id: str
    units: float
    eta_hours: float
    cost: float
    risk: float


class AllocationOut(BaseModel):
    demand_id: str
    assignments: list[AssignmentOut]
    satisfied_units: float
    unmet_units: float
    score: float


class DecisionBriefResponse(BaseModel):
    scenario_id: str
    summary_zh: str
    summary_en: str
    recommended_allocations: list[AllocationOut]
    alternatives: list[dict]
    trade_offs: list[str]
    unmet_demand: list[dict]
    provenance_note: str
    assumptions: list[str]
    provenance_summary: dict[str, int]


def serialize_brief(brief: DecisionBrief) -> DecisionBriefResponse:
    return DecisionBriefResponse(
        scenario_id=brief.scenario_id,
        summary_zh=brief.summary_zh,
        summary_en=brief.summary_en,
        recommended_allocations=[
            AllocationOut(
                demand_id=a.demand_id,
                assignments=[
                    AssignmentOut(
                        port_id=asg.port_id,
                        route_id=asg.route_id,
                        units=asg.units,
                        eta_hours=asg.eta_hours,
                        cost=asg.cost,
                        risk=asg.risk,
                    )
                    for asg in a.assignments
                ],
                satisfied_units=a.satisfied_units,
                unmet_units=a.unmet_units,
                score=a.score,
            )
            for a in brief.recommended_allocations
        ],
        alternatives=list(brief.alternatives),
        trade_offs=list(brief.trade_offs),
        unmet_demand=list(brief.unmet_demand),
        provenance_note=brief.provenance_note,
        assumptions=list(brief.assumptions),
        provenance_summary=brief.provenance_summary,
    )
