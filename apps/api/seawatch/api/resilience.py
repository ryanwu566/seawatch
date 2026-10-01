"""Read-only Edge and resilience health endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from ..live.runtime import get_live_runtime
from ..live.schema import utcnow

router = APIRouter(tags=["resilience"])


@router.get("/edge/health", summary="Local Edge AIS receiver health")
def edge_health() -> dict:
    runtime = get_live_runtime()
    return runtime.edge.consumer.health.snapshot(runtime.edge.store, utcnow())
