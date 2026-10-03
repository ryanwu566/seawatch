"""Detection API: tracks, alerts with explanations, operator feedback, thresholds, evaluation."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..detection.service import get_service
from ..detection.state import STATUSES

router = APIRouter(prefix="/detection", tags=["detection"])


class StatusBody(BaseModel):
    status: str = Field(..., description="One of: " + ", ".join(STATUSES))
    note: str | None = Field(default=None, max_length=2000)
    operator: str = "operator"


class NoteBody(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)
    operator: str = "operator"


class AllowBody(BaseModel):
    mmsi: str
    reason: str = "Operator allow-listed"


def _require(alert_id: str):
    a = get_service().alert(alert_id)
    if a is None:
        raise HTTPException(status_code=404, detail=f"alert not found: {alert_id}")
    return a


@router.get("/scenario", summary="Scenario metadata: zones, receivers, time range")
def scenario() -> dict[str, Any]:
    return get_service().meta()


@router.get("/tracks", summary="Historical and current vessel tracks")
def tracks() -> dict[str, Any]:
    return {"tracks": get_service().tracks()}


@router.get("/alerts", summary="Risk-ranked alerts with reasons")
def alerts(
    as_of: float | None = Query(default=None, description="Replay clock (epoch s): only events detectable by then"),
    include_dismissed: bool = False,
) -> dict[str, Any]:
    items = get_service().alerts(as_of=as_of, include_dismissed=include_dismissed)
    return {"count": len(items), "alerts": [a.summary() for a in items]}


@router.get("/alerts/{alert_id}", summary="One alert: reasons, score breakdown, timeline, uncertainty")
def alert_detail(alert_id: str) -> dict[str, Any]:
    return _require(alert_id).detail()


@router.post("/alerts/{alert_id}/status", summary="Set review status (e.g. false_alarm)")
def set_status(alert_id: str, body: StatusBody) -> dict[str, Any]:
    svc = get_service()
    a = _require(alert_id)
    try:
        svc.store.set_status(a, body.status, body.operator)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if body.note:
        svc.store.add_note(a, body.note, body.operator)
    return _require(alert_id).detail()


@router.post("/alerts/{alert_id}/notes", summary="Add an operator note")
def add_note(alert_id: str, body: NoteBody) -> dict[str, Any]:
    a = _require(alert_id)
    get_service().store.add_note(a, body.text, body.operator)
    return _require(alert_id).detail()


@router.get("/config", summary="Detection thresholds and their descriptions")
def get_config() -> dict[str, Any]:
    return get_service().config()


@router.put("/config", summary="Adjust thresholds; alerts are recomputed")
def put_config(values: dict[str, float]) -> dict[str, Any]:
    svc = get_service()
    svc.set_config(values)
    return svc.config()


@router.post("/config/reset", summary="Restore default thresholds")
def reset_config() -> dict[str, Any]:
    svc = get_service()
    svc.reset_config()
    return svc.config()


@router.get("/evaluation", summary="Measured precision/recall against simulator ground truth")
def evaluation() -> dict[str, Any]:
    return get_service().evaluation()


@router.get("/truth", summary="Ground-truth labels (demo 'reveal answers')")
def truth() -> dict[str, Any]:
    return {"truth": get_service().truth()}


@router.post("/allowlist", summary="Allow-list a vessel for zone entries")
def allow(body: AllowBody) -> dict[str, Any]:
    svc = get_service()
    svc.store.allow(body.mmsi, body.reason)
    return {"allowlist": svc.store.allowlist}


@router.post("/feedback/reset", summary="Clear all operator decisions")
def reset_feedback() -> dict[str, str]:
    get_service().store.clear()
    return {"status": "cleared"}
