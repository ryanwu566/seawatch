"""SeaWatch dashboard API application factory.

Read-only FastAPI surface over existing Phase 3B explainable review-ranking
outputs. It performs no ranking computation and modifies no Phase 1-3 artifacts.
"""

from __future__ import annotations

from fastapi import FastAPI

from .api import alerts, health, tracks

_TITLE = "SeaWatch API"
_DESCRIPTION = (
    "Read-only access to SeaWatch explainable maritime review-ranking outputs. "
    "Alerts are behavioral review candidates for human review, not threat, "
    "hostility, or legality determinations."
)
_VERSION = "0.1.0"


def create_app() -> FastAPI:
    """Build and configure the SeaWatch dashboard API application."""

    app = FastAPI(title=_TITLE, description=_DESCRIPTION, version=_VERSION)
    app.include_router(health.router)
    app.include_router(tracks.router)
    app.include_router(alerts.router)
    return app


app = create_app()
