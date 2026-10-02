"""Serve a prepared Vite build from FastAPI when explicitly enabled."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse, Response

from ..live.config import LiveRuntimeConfig

logger = logging.getLogger("seawatch.web")

_RESERVED_PREFIXES = (
    "assets",
    "live",
    "edge",
    "resilience",
    "offline",
    "health",
    "tracks",
    "alerts",
    "docs",
    "redoc",
    "openapi.json",
)


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def configure_local_web(app: FastAPI, config: LiveRuntimeConfig) -> None:
    """Register local web routes last, without changing the default API app."""

    if not config.serve_web:
        return

    dist = config.web_dist.expanduser().resolve()
    index = dist / "index.html"
    ready = dist.is_dir() and index.is_file()
    if not ready:
        logger.warning("Local web dist is unavailable or invalid: %s", dist)

    def unavailable() -> PlainTextResponse:
        return PlainTextResponse(
            "SeaWatch local web build is unavailable. Build apps/web first.",
            status_code=503,
        )

    def index_response() -> Response:
        if not ready:
            return unavailable()
        return FileResponse(
            index,
            media_type="text/html",
            headers={"Cache-Control": "no-cache"},
        )

    @app.api_route("/", methods=["GET", "HEAD"], include_in_schema=False)
    def local_index() -> Response:
        return index_response()

    @app.api_route(
        "/assets/{asset_path:path}", methods=["GET", "HEAD"], include_in_schema=False
    )
    def local_asset(asset_path: str) -> Response:
        if not ready:
            raise HTTPException(status_code=404, detail="asset not found")
        assets = (dist / "assets").resolve()
        candidate = (assets / asset_path).resolve()
        if not _is_within(candidate, assets) or not candidate.is_file():
            raise HTTPException(status_code=404, detail="asset not found")
        return FileResponse(
            candidate,
            headers={"Cache-Control": "public, max-age=31536000, immutable"},
        )

    @app.api_route(
        "/{client_path:path}", methods=["GET", "HEAD"], include_in_schema=False
    )
    def local_spa(client_path: str) -> Response:
        first = client_path.partition("/")[0]
        if first in _RESERVED_PREFIXES or Path(client_path).suffix:
            raise HTTPException(status_code=404, detail="not found")
        return index_response()
