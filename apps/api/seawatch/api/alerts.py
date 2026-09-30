"""Alerts endpoint router.

Alerts are behavioral review candidates ranked by review priority. They surface
unusual patterns and behavior deviations for human review only.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from ..schemas.alert import AlertDetail, AlertListResponse
from ..services import alert_service
from ..services.artifacts import MissingArtifactError

router = APIRouter(tags=["alerts"])

# Cap page size so the dashboard can never request the full ~28k-row frame.
_MAX_LIMIT = 200


@router.get("/alerts", response_model=AlertListResponse, summary="List ranked review candidates")
def get_alerts(
    method: str | None = Query(
        default=None,
        description="Restrict to a single ranking method (e.g. empirical_percentile).",
    ),
    shortlisted_only: bool = Query(
        default=False,
        description="Return only candidates within the review budget.",
    ),
    dedupe_by_track: bool = Query(
        default=False,
        description="Keep only the highest-priority window per track.",
    ),
    limit: int = Query(
        default=20,
        ge=1,
        le=_MAX_LIMIT,
        description="Maximum candidates to return (page size).",
    ),
    offset: int = Query(default=0, ge=0, description="Number of leading candidates to skip."),
) -> AlertListResponse:
    """Return a page of ranked review candidates.

    List items are slim (no full explanation_reasons); load explanations,
    supporting features, and data quality via GET /alerts/{alert_id}.
    """

    try:
        page = alert_service.list_alerts(
            method=method,
            shortlisted_only=shortlisted_only,
            dedupe_by_track=dedupe_by_track,
            limit=limit,
            offset=offset,
        )
    except MissingArtifactError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    return AlertListResponse(
        count=len(page.items),
        total=page.total,
        limit=limit,
        offset=offset,
        alerts=page.items,
    )


@router.get("/alerts/{alert_id}", response_model=AlertDetail, summary="Get one review candidate")
def get_alert(alert_id: str) -> AlertDetail:
    """Return the ranking result, explanation, supporting features, and data quality."""

    try:
        alert = alert_service.get_alert(alert_id)
    except MissingArtifactError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    if alert is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"alert not found: {alert_id}",
        )
    return alert
