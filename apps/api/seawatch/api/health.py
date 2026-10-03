"""Health endpoint router."""

from __future__ import annotations

from fastapi import APIRouter

from ..historical.store import get_historical_baseline_store

router = APIRouter(tags=["health"])

_SERVICE_NAME = "seawatch-api"


@router.get("/health", summary="Service liveness check")
def get_health() -> dict[str, str]:
    """Return liveness plus observed component initialization state."""

    return {
        "status": "ok",
        "service": _SERVICE_NAME,
        "historical": get_historical_baseline_store().status,
    }
