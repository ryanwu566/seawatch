"""Resilience Logistics API router (Phase 9 RESPOND).

Additive, isolated, read + one pure compute endpoint under ``/logistics``. It
touches no ``/live/*``, ``/resilience/*``, or ``/edge/*`` route and shares no
mutable state with Phase 8. All compute is pure (no outbound network/DB/LLM).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status

from ..logistics import service
from ..logistics.scoring import ScoringError
from ..logistics.schemas import (
    DecisionBriefResponse,
    ScenarioListResponse,
    SimulateRequest,
    serialize_brief,
)

logger = logging.getLogger("seawatch.logistics")

router = APIRouter(prefix="/logistics", tags=["logistics"])

if service.get_dataset() is None:
    logger.error(
        "Logistics scenario dataset failed to load; /logistics will serve an "
        "empty scenario list. Existing SeaWatch endpoints are unaffected."
    )


@router.get(
    "/scenarios",
    response_model=ScenarioListResponse,
    summary="List civilian disruption scenarios",
)
def get_scenarios() -> ScenarioListResponse:
    scenarios = service.list_scenarios()
    return ScenarioListResponse(count=len(scenarios), scenarios=scenarios)


@router.get(
    "/scenarios/{scenario_id}",
    summary="Full scenario context for the UI",
)
def get_scenario(scenario_id: str) -> dict:
    try:
        return service.scenario_context(scenario_id)
    except service.ScenarioNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"unknown scenario: {scenario_id}",
        ) from exc


@router.post(
    "/simulate",
    response_model=DecisionBriefResponse,
    summary="Compute a resilience decision brief (pure, for human review)",
)
def post_simulate(request: SimulateRequest) -> DecisionBriefResponse:
    weights = request.weights.to_dict() if request.weights else None
    try:
        brief = service.simulate(request.scenario_id, weights)
    except service.ScenarioNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"unknown scenario: {request.scenario_id}",
        ) from exc
    except ScoringError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"invalid weights: {exc}",
        ) from exc
    return serialize_brief(brief)
