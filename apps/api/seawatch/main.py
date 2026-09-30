"""SeaWatch dashboard API application factory.

Read-only FastAPI surface over existing Phase 3B explainable review-ranking
outputs. It performs no ranking computation and modifies no Phase 1-3 artifacts.
"""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import alerts, health, tracks

_TITLE = "SeaWatch API"
_DESCRIPTION = (
    "Read-only access to SeaWatch explainable maritime review-ranking outputs. "
    "Alerts are behavioral review candidates for human review, not threat, "
    "hostility, or legality determinations."
)
_VERSION = "0.1.0"

# The dashboard runs on the Vite dev server (default port 5173) on a different
# origin than the API (port 8000). Browsers require the API to return CORS
# headers or they block the JS from reading the response. Origins can be
# overridden via SEAWATCH_CORS_ORIGINS (comma-separated).
_DEFAULT_CORS_ORIGINS = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
)


def _cors_origins() -> list[str]:
    raw = os.environ.get("SEAWATCH_CORS_ORIGINS")
    if raw:
        origins = [origin.strip() for origin in raw.split(",") if origin.strip()]
        if origins:
            return origins
    return list(_DEFAULT_CORS_ORIGINS)


def create_app() -> FastAPI:
    """Build and configure the SeaWatch dashboard API application."""

    app = FastAPI(title=_TITLE, description=_DESCRIPTION, version=_VERSION)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins(),
        allow_methods=["GET"],
        allow_headers=["*"],
    )
    app.include_router(health.router)
    app.include_router(tracks.router)
    app.include_router(alerts.router)
    return app


app = create_app()
