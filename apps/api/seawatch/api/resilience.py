"""Read-only Edge and resilience health endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from ..live.runtime import get_live_runtime, get_resilience_status
from ..live.schema import utcnow

router = APIRouter(tags=["resilience"])


@router.get("/edge/health", summary="Local Edge AIS receiver health")
def edge_health() -> dict:
    runtime = get_live_runtime()
    return runtime.edge.consumer.health.snapshot(runtime.edge.store, utcnow())


def _source_payload(source) -> dict:
    return {
        "source": source.source,
        "fresh": source.fresh,
        "message_age_seconds": source.message_age_seconds,
        "vessel_count": source.vessel_count,
        "connected": source.connected,
        "input_kind": source.input_kind.value if source.input_kind else None,
    }


@router.get("/resilience/status", summary="Active Cloud/Edge resilience mode")
def resilience_status() -> dict:
    status = get_resilience_status()
    return {
        "mode": status.mode.value,
        "coverage": status.coverage.value,
        "simulated": status.simulated,
        "internet_available": status.cloud.fresh,
        "power_mode": status.power_mode.value,
        "cloud": _source_payload(status.cloud),
        "edge": _source_payload(status.edge),
    }
