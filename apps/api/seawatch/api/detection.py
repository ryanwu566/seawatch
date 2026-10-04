"""Detection API: tracks, alerts with explanations, operator feedback, thresholds, evaluation."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..detection.service import (
    available_regions,
    get_historical_summary,
    get_service,
    set_region,
)
from ..detection.state import STATUSES
from ..live.runtime import get_live_runtime

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


DetectionSource = Literal["scenario", "live"]


def _require(alert_id: str, source: DetectionSource = "scenario"):
    if source == "live":
        alert = get_live_runtime().live_detection.public_alert(alert_id)
        if alert is None:
            raise HTTPException(status_code=404, detail=f"alert not found: {alert_id}")
        return alert
    a = get_service().alert(alert_id)
    if a is None:
        raise HTTPException(status_code=404, detail=f"alert not found: {alert_id}")
    return a


class RegionBody(BaseModel):
    id: str


@router.get("/historical", summary="Optional aggregate Historical Runtime context")
def historical() -> dict[str, Any]:
    return get_historical_summary()


@router.get("/regions", summary="Regions the console can monitor, and which is active")
def regions() -> dict[str, Any]:
    return {"active": get_service().region, "regions": available_regions()}


@router.post("/region", summary="Switch the active region")
def select_region(body: RegionBody) -> dict[str, Any]:
    ok = {r["id"]: r["available"] for r in available_regions()}
    if not ok.get(body.id):
        raise HTTPException(status_code=404, detail=f"region not available: {body.id}")
    set_region(body.id)
    return {"active": body.id}


@router.get("/scenario", summary="Scenario metadata: zones, receivers, time range")
def scenario(source: DetectionSource = "scenario") -> dict[str, Any]:
    if source == "live":
        return get_live_runtime().live_detection.public_meta()
    return get_service().meta()


@router.get("/tracks", summary="Historical and current vessel tracks")
def tracks(source: DetectionSource = "scenario") -> dict[str, Any]:
    if source == "live":
        runtime = get_live_runtime().live_detection
        return {
            **runtime.snapshot().to_public_dict(),
            "tracks": runtime.public_tracks(),
        }
    return {"tracks": get_service().tracks()}


@router.get("/alerts", summary="Risk-ranked alerts with reasons")
def alerts(
    as_of: float | None = Query(default=None, description="Replay clock (epoch s): only events detectable by then"),
    include_dismissed: bool = False,
    source: DetectionSource = "scenario",
) -> dict[str, Any]:
    if source == "live":
        if as_of is not None:
            raise HTTPException(
                status_code=422,
                detail="Live Detection does not support replay time",
            )
        runtime = get_live_runtime().live_detection
        items = runtime.public_alerts(include_dismissed=include_dismissed)
        return {
            **runtime.snapshot().to_public_dict(),
            "count": len(items),
            "alerts": items,
        }
    items = get_service().alerts(as_of=as_of, include_dismissed=include_dismissed)
    return {"count": len(items), "alerts": [a.summary() for a in items]}


@router.get("/alerts/{alert_id}", summary="One alert: reasons, score breakdown, timeline, uncertainty")
def alert_detail(
    alert_id: str,
    source: DetectionSource = "scenario",
) -> dict[str, Any]:
    a = _require(alert_id, source)
    if source == "live":
        return a
    d = a.detail()
    try:  # advisory path reviews of the same vessels in the same period (message-level regions only)
        revs, _, _ = get_service().path_reviews()
        d["path_reviews"] = [r.to_dict() for r in revs if r.mmsi in a.mmsis and r.flag and r.t1 >= a.t_start - 86400 and r.t0 <= a.t_end + 86400][:12]
    except Exception:  # noqa: BLE001 - advisory only
        d["path_reviews"] = []
    return d


@router.post("/alerts/{alert_id}/status", summary="Set review status (e.g. false_alarm)")
def set_status(
    alert_id: str,
    body: StatusBody,
    source: DetectionSource = "scenario",
) -> dict[str, Any]:
    if source == "live":
        runtime = get_live_runtime().live_detection
        try:
            result = runtime.set_alert_status(
                alert_id,
                body.status,
                operator=body.operator,
                note=body.note,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if result is None:
            raise HTTPException(status_code=404, detail=f"alert not found: {alert_id}")
        return result
    svc = get_service()
    a = _require(alert_id, source)
    try:
        svc.store.set_status(a, body.status, body.operator)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if body.note:
        svc.store.add_note(a, body.note, body.operator)
    return _require(alert_id, source).detail()


@router.post("/alerts/{alert_id}/notes", summary="Add an operator note")
def add_note(
    alert_id: str,
    body: NoteBody,
    source: DetectionSource = "scenario",
) -> dict[str, Any]:
    if source == "live":
        result = get_live_runtime().live_detection.add_alert_note(
            alert_id,
            body.text,
            operator=body.operator,
        )
        if result is None:
            raise HTTPException(status_code=404, detail=f"alert not found: {alert_id}")
        return result
    a = _require(alert_id, source)
    get_service().store.add_note(a, body.text, body.operator)
    return _require(alert_id, source).detail()


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


@router.get("/ml", summary="ML models: benchmark vs rules on the held-out day")
def ml_report() -> dict[str, Any]:
    svc = get_service()
    return {"trained": svc.ml_models is not None, "region": svc.region, "benchmark": svc.ml_report}


@router.get("/assessment", summary="Detection quality, noise funnel and factor breakdown")
def assessment() -> dict[str, Any]:
    return get_service().assessment()


@router.get("/rulebook", summary="Every rule: what, why suspicious, thresholds (live), benign explanations, limits")
def rulebook() -> dict[str, Any]:
    from ..detection.rulebook import build

    svc = get_service()
    return build(svc.cfg, svc.hourly)


@router.get("/layers", summary="Map layers: submarine cables, landing points and Taiwan's modelled maritime limits")
def layers() -> dict[str, Any]:
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parents[4] / "data" / "geo"

    def read(name: str) -> dict[str, Any]:
        try:
            return json.loads((root / name).read_text(encoding="utf8"))
        except (OSError, ValueError):
            return {"type": "FeatureCollection", "features": []}

    return {"cables": read("taiwan_cables.geojson"), "landing": read("taiwan_landing_points.geojson"), "limits": read("taiwan_zone_lines.geojson"),
            "attribution": "Cables: TeleGeography Submarine Cable Map (CC BY-NC-SA 4.0), approximate. Limits: modelled from public coastlines, not legal baselines."}


class ReviewDecision(BaseModel):
    decision: str
    operator: str = "analyst"
    note: str = ""


@router.get("/path-reviews", summary="Path-analysis agent: reviews of slow research-vessel windows (advisory)")
def path_reviews(flagged_only: bool = True) -> dict[str, Any]:
    from ..detection import pathagent

    revs, funnel, reviewer = get_service().path_reviews()
    items = [r for r in revs if r.flag or not flagged_only]
    return {"reviewer": reviewer, "funnel": funnel, "categories": pathagent.CATEGORIES, "count": len(items),
            "episodes": pathagent.episodes(revs), "reviews": [r.to_dict() for r in sorted(items, key=lambda r: (-r.confidence, r.t0))][:500],
            "note": "Advisory interpretation of the path. It never changes deterministic alerts; accept / reject decisions are stored as training labels."}


@router.get("/path-reviews/{review_id}/image", summary="Rendered track picture the agent looks at")
def path_review_image(review_id: str):
    from fastapi.responses import Response

    import numpy as np

    from ..detection import pathagent

    svc = get_service()
    revs, _, _ = svc.path_reviews()
    r = next((x for x in revs if x.id == review_id), None)
    if r is None:
        raise HTTPException(status_code=404, detail="unknown review")
    tr = next(t for t in svc.scenario.tracks if t.mmsi == r.mmsi)
    i, j = int(np.searchsorted(tr.t, r.t0, "left")), int(np.searchsorted(tr.t, r.t1, "right"))
    return Response(content=pathagent.render_png(tr, i, j), media_type="image/png")


@router.post("/path-reviews/{review_id}/decision", summary="Analyst accepts or rejects an agent review")
def path_review_decision(review_id: str, body: ReviewDecision) -> dict[str, Any]:
    svc = get_service()
    revs, _, _ = svc.path_reviews()
    if not any(x.id == review_id for x in revs):
        raise HTTPException(status_code=404, detail="unknown review")
    try:
        svc.review_store().decide(review_id, body.decision, body.operator, body.note)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"id": review_id, "decision": body.decision}


@router.get("/path-reviews-export", summary="Accepted / rejected reviews as confirmed_paths.csv rows")
def path_review_export() -> dict[str, Any]:
    svc = get_service()
    revs, _, _ = svc.path_reviews()
    return {"csv": svc.review_store().export_labels(revs)}


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
