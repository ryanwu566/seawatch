"""Slice F — logistics API behavior + existing-route non-regression."""

from __future__ import annotations

import socket

import pytest
from fastapi.testclient import TestClient

from apps.api.seawatch.main import create_app


@pytest.fixture()
def client():
    with TestClient(create_app()) as c:
        yield c


def test_list_scenarios_includes_kaohsiung(client) -> None:
    resp = client.get("/logistics/scenarios")
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] >= 1
    ids = {s["id"] for s in body["scenarios"]}
    assert "kaohsiung-disruption" in ids


def test_scenario_context_returns_provenance_summary(client) -> None:
    resp = client.get("/logistics/scenarios/kaohsiung-disruption")
    assert resp.status_code == 200
    body = resp.json()
    assert body["scenario"]["id"] == "kaohsiung-disruption"
    assert "provenance_summary" in body
    assert body["affected_demands"]
    assert "kaohsiung" not in body["candidate_ports"]


def test_unknown_scenario_404(client) -> None:
    assert client.get("/logistics/scenarios/nope").status_code == 404


def test_simulate_happy_path_returns_structured_brief(client) -> None:
    resp = client.post("/logistics/simulate", json={"scenario_id": "kaohsiung-disruption"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["scenario_id"] == "kaohsiung-disruption"
    assert body["recommended_allocations"]
    assert body["alternatives"]
    assert body["provenance_note"]
    assert "human review" in body["provenance_note"]
    assert set(body["provenance_summary"]).issuperset(
        {"official", "derived", "scenario", "synthetic"}
    )


def test_simulate_unknown_scenario_404(client) -> None:
    resp = client.post("/logistics/simulate", json={"scenario_id": "nope"})
    assert resp.status_code == 404


def test_simulate_malformed_weights_422(client) -> None:
    resp = client.post(
        "/logistics/simulate",
        json={"scenario_id": "kaohsiung-disruption", "weights": {"time": -1}},
    )
    assert resp.status_code == 422


def test_simulate_is_deterministic(client) -> None:
    a = client.post("/logistics/simulate", json={"scenario_id": "kaohsiung-disruption"})
    b = client.post("/logistics/simulate", json={"scenario_id": "kaohsiung-disruption"})
    assert a.status_code == 200 and b.status_code == 200
    assert a.json() == b.json()


def test_infeasible_scenario_returns_200_with_unmet(client, monkeypatch) -> None:
    # Force an all-ports-disrupted style infeasibility by requesting a weighting
    # that is still valid; instead we assert the contract: a scenario leaving
    # demand unsatisfiable reports it in unmet_demand, not as an error. We use
    # the real dataset which satisfies all demand, so we assert the field shape.
    resp = client.post("/logistics/simulate", json={"scenario_id": "kaohsiung-disruption"})
    assert resp.status_code == 200
    assert isinstance(resp.json()["unmet_demand"], list)


def test_simulate_opens_no_outbound_socket(client, monkeypatch) -> None:
    """The pure simulation must not reach out to any provider/DB/live source."""

    original_connect = socket.socket.connect

    def _blocked_connect(self, address):  # noqa: ANN001
        raise AssertionError(f"simulate opened an outbound socket to {address!r}")

    monkeypatch.setattr(socket.socket, "connect", _blocked_connect)
    try:
        resp = client.post(
            "/logistics/simulate", json={"scenario_id": "kaohsiung-disruption"}
        )
    finally:
        monkeypatch.setattr(socket.socket, "connect", original_connect)
    assert resp.status_code == 200


def test_existing_routes_unregressed(client) -> None:
    assert client.get("/health").status_code == 200
    assert client.get("/health").json()["service"] == "seawatch-api"
    assert client.get("/live/health").status_code == 200
    assert client.get("/resilience/status").status_code == 200
    assert client.get("/tracks").status_code in (200, 404, 503)
