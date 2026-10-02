from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.api.seawatch.live.config import LiveRuntimeConfig
from apps.api.seawatch.main import create_app
from apps.api.seawatch.web.serving import configure_local_web


def _config(dist: Path, *, enabled: bool = True) -> LiveRuntimeConfig:
    return replace(LiveRuntimeConfig.from_env({}), serve_web=enabled, web_dist=dist)


def _app() -> FastAPI:
    app = FastAPI()
    for path in (
        "/health",
        "/live/health",
        "/live/vessels",
        "/resilience/status",
        "/edge/health",
    ):
        app.get(path)(lambda path=path: {"route": path})
    return app


def _dist(tmp_path: Path) -> Path:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(
        "<html><div id='root'>SeaWatch</div></html>", encoding="utf-8"
    )
    (dist / "assets" / "app-123.js").write_text("window.SEAWATCH=true", encoding="utf-8")
    return dist


def test_disabled_default_registers_no_web_routes_or_dist_lookup(tmp_path: Path) -> None:
    app = _app()
    before = tuple(route.path for route in app.routes)
    lifespan_before = app.router.lifespan_context

    configure_local_web(app, _config(tmp_path / "missing", enabled=False))

    assert tuple(route.path for route in app.routes) == before
    assert app.router.lifespan_context is lifespan_before
    assert TestClient(app).get("/").status_code == 404


def test_enabled_serves_index_and_hashed_asset_with_mime_and_cache(tmp_path: Path) -> None:
    dist = _dist(tmp_path)
    app = _app()
    configure_local_web(app, _config(dist))
    client = TestClient(app)

    root = client.get("/")
    asset = client.get("/assets/app-123.js")

    assert root.status_code == 200
    assert "SeaWatch" in root.text
    assert root.headers["cache-control"] == "no-cache"
    assert asset.status_code == 200
    assert asset.headers["content-type"].startswith("text/javascript")
    assert asset.headers["cache-control"] == "public, max-age=31536000, immutable"


def test_missing_or_invalid_dist_returns_local_503_but_keeps_api_available(
    tmp_path: Path,
    caplog,
) -> None:
    for dist in (tmp_path / "missing", tmp_path / "not-a-directory"):
        if dist.name == "not-a-directory":
            dist.write_text("not a dist", encoding="utf-8")
        app = _app()
        configure_local_web(app, _config(dist))
        client = TestClient(app)
        assert client.get("/").status_code == 503
        assert client.get("/health").json() == {"route": "/health"}

    messages = [
        record.message
        for record in caplog.records
        if "web dist" in record.message.lower()
    ]
    assert len(messages) == 2


def test_api_precedence_spa_fallback_assets_and_traversal(tmp_path: Path) -> None:
    dist = _dist(tmp_path)
    secret = tmp_path / "secret.txt"
    secret.write_text("do-not-serve", encoding="utf-8")
    app = _app()
    configure_local_web(app, _config(dist))
    client = TestClient(app)

    for path in (
        "/health",
        "/live/health",
        "/live/vessels",
        "/resilience/status",
        "/edge/health",
    ):
        response = client.get(path)
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/json")

    assert client.get("/vessel/example").status_code == 200
    assert "SeaWatch" in client.get("/vessel/example").text
    assert client.get("/assets/missing.js").status_code == 404
    assert client.get("/assets/%2e%2e/secret.txt").status_code == 404
    assert "do-not-serve" not in client.get("/assets/%2e%2e/secret.txt").text
    assert client.get("/missing.css").status_code == 404
    # Reserved future API/file namespaces must never fall through to the SPA.
    assert client.get("/offline/taiwan.pmtiles").status_code == 404


def test_application_factory_is_unchanged_when_serving_flag_is_absent(
    monkeypatch,
) -> None:
    monkeypatch.delenv("SEAWATCH_SERVE_WEB", raising=False)
    monkeypatch.setenv("SEAWATCH_WEB_DIST", "this-path-must-not-be-read")

    app = create_app()

    assert not any(route.path in {"/", "/{client_path:path}"} for route in app.routes)
    assert TestClient(app).get("/").status_code == 404


def test_application_factory_registers_web_after_real_api_routes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    dist = _dist(tmp_path)
    monkeypatch.setenv("SEAWATCH_SERVE_WEB", "true")
    monkeypatch.setenv("SEAWATCH_WEB_DIST", str(dist))

    app = create_app()
    paths = [route.path for route in app.routes]
    client = TestClient(app)

    assert paths.index("/live/health") < paths.index("/{client_path:path}")
    assert paths.index("/resilience/status") < paths.index("/{client_path:path}")
    assert client.get("/live/health").headers["content-type"].startswith(
        "application/json"
    )
    assert client.get("/vessel/example").headers["content-type"].startswith("text/html")


def test_pmtiles_get_head_and_single_byte_ranges(tmp_path: Path) -> None:
    dist = _dist(tmp_path)
    archive = tmp_path / "taiwan.pmtiles"
    archive.write_bytes(b"0123456789abcdef")
    config = replace(_config(dist), pmtiles_file=archive)
    app = _app()
    configure_local_web(app, config)
    client = TestClient(app)

    full = client.get("/offline/taiwan.pmtiles")
    head = client.head("/offline/taiwan.pmtiles")
    bounded = client.get("/offline/taiwan.pmtiles", headers={"Range": "bytes=0-3"})
    open_ended = client.get("/offline/taiwan.pmtiles", headers={"Range": "bytes=12-"})
    suffix = client.get("/offline/taiwan.pmtiles", headers={"Range": "bytes=-4"})

    assert full.status_code == 200 and full.content == b"0123456789abcdef"
    assert full.headers["accept-ranges"] == "bytes"
    assert head.status_code == 200 and head.content == b""
    assert head.headers["content-length"] == "16"
    assert bounded.status_code == 206 and bounded.content == b"0123"
    assert bounded.headers["content-range"] == "bytes 0-3/16"
    assert open_ended.status_code == 206 and open_ended.content == b"cdef"
    assert suffix.status_code == 206 and suffix.content == b"cdef"


def test_pmtiles_rejects_invalid_ranges_and_missing_or_non_file_paths(tmp_path: Path) -> None:
    dist = _dist(tmp_path)
    archive = tmp_path / "taiwan.pmtiles"
    archive.write_bytes(b"0123456789abcdef")
    app = _app()
    configure_local_web(app, replace(_config(dist), pmtiles_file=archive))
    client = TestClient(app)

    for value in ("bytes=99-", "bytes=nope", "bytes=0-1,3-4", "items=0-1"):
        response = client.get("/offline/taiwan.pmtiles", headers={"Range": value})
        assert response.status_code == 416
        assert response.headers["content-range"] == "bytes */16"

    for unavailable in (tmp_path / "missing.pmtiles", tmp_path):
        missing_app = _app()
        configure_local_web(
            missing_app,
            replace(_config(dist), pmtiles_file=unavailable),
        )
        assert TestClient(missing_app).get("/offline/taiwan.pmtiles").status_code == 404
