from __future__ import annotations

from collections.abc import Callable

from fastapi.testclient import TestClient
import pytest

from apps.api.seawatch.historical.schema import (
    DATA_SOURCE_GFW_PRESENCE,
    Provenanced,
    TypicalRoute,
    VesselBaseline,
    VesselHistorySummary,
)
from apps.api.seawatch.main import create_app


PUBLIC_ID = "v_opaque123"


def _baseline(*, sufficient: bool = True) -> VesselBaseline:
    routes = (
        TypicalRoute(
            route_key="historical-cohort",
            occurrence_count=5,
            corridor_centerline=((120.0, 22.0), (120.2, 22.1)),
            corridor_width_p90_m=Provenanced(850.0, "derived"),
            provenance="derived",
        ),
    ) if sufficient else ()
    return VesselBaseline(
        vessel_key=PUBLIC_ID,
        history_summary=VesselHistorySummary(
            observed_day_count=Provenanced(5, "derived"),
            first_observed_utc=Provenanced("2026-09-01T00:00:00Z", "observed"),
            last_observed_utc=Provenanced("2026-09-05T02:00:00Z", "observed"),
            total_observations=Provenanced(15, "derived"),
            data_source=DATA_SOURCE_GFW_PRESENCE,
        ),
        typical_routes=routes,
        historical_track_count=5 if sufficient else 2,
        confidence=Provenanced("HIGH" if sufficient else "LOW", "derived"),
        sufficient=sufficient,
        data_source=DATA_SOURCE_GFW_PRESENCE,
    )


@pytest.fixture(autouse=True)
def _reset_store() -> None:
    try:
        from apps.api.seawatch.historical.store import (
            reset_historical_baseline_store,
        )
    except ModuleNotFoundError:
        yield
        return

    reset_historical_baseline_store()
    yield
    reset_historical_baseline_store()


def _client_with_store(monkeypatch, store) -> TestClient:
    from apps.api.seawatch.api import historical as historical_api

    monkeypatch.setattr(
        historical_api,
        "get_historical_baseline_store",
        lambda: store,
    )
    return TestClient(create_app())


def test_valid_opaque_id_returns_sufficient_baseline(monkeypatch) -> None:
    from apps.api.seawatch.historical.store import HistoricalBaselineStore

    client = _client_with_store(
        monkeypatch,
        HistoricalBaselineStore(lambda: {PUBLIC_ID: _baseline()}),
    )

    response = client.get(f"/historical/vessels/{PUBLIC_ID}/baseline")

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "vessel-baseline-1"
    assert body["vessel_key"] == PUBLIC_ID
    assert body["history_summary"]["observed_day_count"] == {
        "value": 5,
        "provenance": "derived",
    }
    assert body["typical_routes"][0]["corridor_centerline"] == [
        [120.0, 22.0],
        [120.2, 22.1],
    ]


def test_insufficient_matched_baseline_is_http_200(monkeypatch) -> None:
    from apps.api.seawatch.historical.store import HistoricalBaselineStore

    baseline = _baseline(sufficient=False)
    client = _client_with_store(
        monkeypatch,
        HistoricalBaselineStore(lambda: {PUBLIC_ID: baseline}),
    )

    response = client.get(f"/historical/vessels/{PUBLIC_ID}/baseline")

    assert response.status_code == 200
    assert response.json()["sufficient"] is False
    assert response.json()["historical_track_count"] == 2


def test_unmatched_vessel_returns_generic_404(monkeypatch) -> None:
    from apps.api.seawatch.historical.store import HistoricalBaselineStore

    client = _client_with_store(monkeypatch, HistoricalBaselineStore(lambda: {}))

    response = client.get(f"/historical/vessels/{PUBLIC_ID}/baseline")

    assert response.status_code == 404
    assert response.json() == {"detail": "Historical baseline not found"}
    assert PUBLIC_ID not in response.text


@pytest.mark.parametrize(
    "failure",
    [
        ValueError("missing configuration"),
        FileNotFoundError("missing data"),
        RuntimeError("identity or privacy failure"),
    ],
)
def test_initialization_failure_returns_generic_503(monkeypatch, failure: Exception) -> None:
    from apps.api.seawatch.historical.store import HistoricalBaselineStore

    def fail() -> dict[str, VesselBaseline]:
        raise failure

    client = _client_with_store(monkeypatch, HistoricalBaselineStore(fail))

    response = client.get(f"/historical/vessels/{PUBLIC_ID}/baseline")

    assert response.status_code == 503
    assert response.json() == {"detail": "Historical baseline unavailable"}
    assert PUBLIC_ID not in response.text
    assert str(failure) not in response.text


@pytest.mark.parametrize("public_id", ["416000001", "v_", "not-opaque", "v_bad id"])
def test_malformed_or_non_opaque_id_returns_generic_400(
    monkeypatch,
    public_id: str,
) -> None:
    from apps.api.seawatch.historical.store import HistoricalBaselineStore

    client = _client_with_store(monkeypatch, HistoricalBaselineStore(lambda: {}))

    response = client.get(f"/historical/vessels/{public_id}/baseline")

    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid public vessel identifier"}
    assert public_id not in response.text


def test_success_response_contains_no_raw_identifier_fields_or_values(monkeypatch) -> None:
    from apps.api.seawatch.historical.store import HistoricalBaselineStore

    client = _client_with_store(
        monkeypatch,
        HistoricalBaselineStore(lambda: {PUBLIC_ID: _baseline()}),
    )

    response = client.get(f"/historical/vessels/{PUBLIC_ID}/baseline")

    assert response.status_code == 200
    body = response.text.casefold()
    for forbidden in (
        "mmsi",
        "imo",
        "callsign",
        "call_sign",
        "ship_name",
        "shipname",
        "vesselid",
        "raw-gfw-vessel-id",
        "416000001",
    ):
        assert forbidden not in body


def test_lazy_store_builds_once_and_repeated_lookup_is_reused() -> None:
    from apps.api.seawatch.historical.store import HistoricalBaselineStore

    calls = 0

    def build() -> dict[str, VesselBaseline]:
        nonlocal calls
        calls += 1
        return {PUBLIC_ID: _baseline()}

    store = HistoricalBaselineStore(build)

    assert calls == 0
    assert store.get(PUBLIC_ID) == _baseline()
    assert store.get(PUBLIC_ID) == _baseline()
    assert store.get("v_other") is None
    assert calls == 1


def test_failed_initialization_is_cached_for_process_lifetime() -> None:
    from apps.api.seawatch.historical.store import (
        HistoricalBaselineStore,
        HistoricalBaselineUnavailableError,
    )

    calls = 0

    def fail() -> dict[str, VesselBaseline]:
        nonlocal calls
        calls += 1
        raise RuntimeError("sensitive initialization detail")

    store = HistoricalBaselineStore(fail)

    for _ in range(2):
        with pytest.raises(
            HistoricalBaselineUnavailableError,
            match="Historical baseline unavailable",
        ) as caught:
            store.get(PUBLIC_ID)
        assert "sensitive" not in str(caught.value)
    assert calls == 1


def test_process_store_uses_live_registry_and_reset_hook_rebuilds(monkeypatch) -> None:
    from apps.api.seawatch.historical import store as store_module

    calls = 0
    seen_registry = []

    class ConfiguredRuntime:
        class Config:
            identity_key = "configured-key"

        config = Config()
        identity_registry = object()

    def build(*, identity_registry) -> dict[str, VesselBaseline]:
        nonlocal calls
        calls += 1
        seen_registry.append(identity_registry)
        return {PUBLIC_ID: _baseline()}

    monkeypatch.setattr(store_module, "get_live_runtime", lambda: ConfiguredRuntime())
    monkeypatch.setattr(store_module, "build_gfw_baselines", build)

    first = store_module.get_historical_baseline_store()
    assert first.get(PUBLIC_ID) == _baseline()
    assert first.get(PUBLIC_ID) == _baseline()
    assert calls == 1

    store_module.reset_historical_baseline_store()
    second = store_module.get_historical_baseline_store()
    assert second is not first
    assert second.get(PUBLIC_ID) == _baseline()
    assert calls == 2
    assert seen_registry == [ConfiguredRuntime.identity_registry] * 2


def test_process_store_fails_closed_without_configured_identity_key(monkeypatch) -> None:
    from apps.api.seawatch.historical import store as store_module

    class UnconfiguredRuntime:
        class Config:
            identity_key = None

        config = Config()
        identity_registry = object()

    build: Callable[..., dict[str, VesselBaseline]] = pytest.fail
    monkeypatch.setattr(store_module, "get_live_runtime", lambda: UnconfiguredRuntime())
    monkeypatch.setattr(store_module, "build_gfw_baselines", build)

    with pytest.raises(
        store_module.HistoricalBaselineUnavailableError,
        match="Historical baseline unavailable",
    ):
        store_module.get_historical_baseline_store().get(PUBLIC_ID)
