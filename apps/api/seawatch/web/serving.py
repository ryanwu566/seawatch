"""Serve a prepared Vite build from FastAPI when explicitly enabled."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, PlainTextResponse, Response, StreamingResponse

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


def _byte_range(value: str, size: int) -> tuple[int, int] | None:
    if not value.startswith("bytes=") or "," in value:
        return None
    spec = value.removeprefix("bytes=")
    if "-" not in spec:
        return None
    start_text, end_text = spec.split("-", 1)
    try:
        if not start_text:
            suffix = int(end_text)
            if suffix <= 0:
                return None
            return max(0, size - suffix), size - 1
        start = int(start_text)
        end = size - 1 if not end_text else int(end_text)
    except ValueError:
        return None
    if start < 0 or start >= size or end < start:
        return None
    return start, min(end, size - 1)


def _file_chunks(path: Path, start: int, length: int):
    with path.open("rb") as handle:
        handle.seek(start)
        remaining = length
        while remaining:
            chunk = handle.read(min(64 * 1024, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


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

    if config.pmtiles_file is not None:
        archive = config.pmtiles_file.expanduser().resolve()

        @app.api_route(
            "/offline/taiwan.pmtiles",
            methods=["GET", "HEAD"],
            include_in_schema=False,
        )
        def local_pmtiles(request: Request) -> Response:
            if not archive.is_file():
                raise HTTPException(status_code=404, detail="PMTiles archive not found")
            size = archive.stat().st_size
            base_headers = {"Accept-Ranges": "bytes"}
            range_value = request.headers.get("range")
            if range_value is None:
                headers = {**base_headers, "Content-Length": str(size)}
                if request.method == "HEAD":
                    return Response(
                        status_code=200,
                        headers=headers,
                        media_type="application/vnd.pmtiles",
                    )
                return StreamingResponse(
                    _file_chunks(archive, 0, size),
                    headers=headers,
                    media_type="application/vnd.pmtiles",
                )

            selected = _byte_range(range_value, size)
            if selected is None:
                return Response(
                    status_code=416,
                    headers={**base_headers, "Content-Range": f"bytes */{size}"},
                )
            start, end = selected
            length = end - start + 1
            headers = {
                **base_headers,
                "Content-Length": str(length),
                "Content-Range": f"bytes {start}-{end}/{size}",
            }
            if request.method == "HEAD":
                return Response(
                    status_code=206,
                    headers=headers,
                    media_type="application/vnd.pmtiles",
                )
            return StreamingResponse(
                _file_chunks(archive, start, length),
                status_code=206,
                headers=headers,
                media_type="application/vnd.pmtiles",
            )

    @app.api_route(
        "/{client_path:path}", methods=["GET", "HEAD"], include_in_schema=False
    )
    def local_spa(client_path: str) -> Response:
        first = client_path.partition("/")[0]
        if first in _RESERVED_PREFIXES or Path(client_path).suffix:
            raise HTTPException(status_code=404, detail="not found")
        return index_response()
