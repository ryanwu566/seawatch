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


@router.get("/alerts", response_model=AlertListResponse, summary="List ranked review candidates")
def get_alerts(
    shortlisted_only: bool = Query(
        default=False,
        description="Return only candidates within the review budget.",
    ),
) -> AlertListResponse:
    """Return ranked review candidates ordered by descending review priority."""

    try:
        alerts = alert_service.list_alerts(shortlisted_only=shortlisted_only)
    except MissingArtifactError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    return AlertListResponse(count=len(alerts), alerts=alerts)


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
