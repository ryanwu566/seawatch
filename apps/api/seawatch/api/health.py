"""Health endpoint router."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["health"])

_SERVICE_NAME = "seawatch-api"


@router.get("/health", summary="Service liveness check")
def get_health() -> dict[str, str]:
    """Return a static liveness payload."""

    return {"status": "ok", "service": _SERVICE_NAME}
