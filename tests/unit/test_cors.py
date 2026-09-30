"""Regression tests for CORS configuration.

The dashboard (Vite dev server, http://localhost:5173) and the API (port 8000)
are different origins. Without CORS headers the browser blocks the JS from
reading responses even though the server returns 200, which surfaced as
"API: offline" in the dashboard. These tests assert the API sends the headers.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from apps.api.seawatch.main import create_app

_VITE_ORIGIN = "http://localhost:5173"


def test_simple_request_includes_cors_header() -> None:
    client = TestClient(create_app())
    response = client.get("/health", headers={"Origin": _VITE_ORIGIN})
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == _VITE_ORIGIN


def test_preflight_request_is_allowed() -> None:
    client = TestClient(create_app())
    response = client.options(
        "/alerts",
        headers={
            "Origin": _VITE_ORIGIN,
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == _VITE_ORIGIN


def test_custom_origins_via_environment(monkeypatch) -> None:
    monkeypatch.setenv("SEAWATCH_CORS_ORIGINS", "http://example.test:4000")
    client = TestClient(create_app())
    response = client.get(
        "/health", headers={"Origin": "http://example.test:4000"}
    )
    assert response.headers.get("access-control-allow-origin") == "http://example.test:4000"
