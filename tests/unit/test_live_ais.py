"""Offline tests for the SeaWatch Phase 7A live real-time AIS foundation.

These tests never touch live internet. They use recorded/minimal Open Waters
frames (captured during Phase 7A smoke testing) to exercise normalization, the
in-memory store, dedup, stale cleanup, trajectory retention, reconnect state,
and the /live endpoints. Credentials are never required or exposed.
"""

from __future__ import annotations

import json
from datetime import timedelta

from fastapi.testclient import TestClient

from apps.api.seawatch import live as live_pkg
from apps.api.seawatch.live.ingest import AisIngestConsumer
from apps.api.seawatch.live.open_waters import OpenWatersProvider
from apps.api.seawatch.live.provider import TAIWAN_BBOX, BoundingBox
from apps.api.seawatch.live.schema import LiveVesselObservation, utcnow
from apps.api.seawatch.live.store import LiveVesselStore
from apps.api.seawatch.main import create_app


# --- Recorded real Open Waters frames (Phase 7A, 2026-10-01) ---------------- #
WS_WELCOME = {
    "type": "welcome",
    "sub": "anon:0.0.0.0",
    "role": "anonymous",
    "limits": {"conns": 2, "rate": 20, "area": 100, "mmsis": 10, "connects_per_min": 20},
}

WS_POSITION = {
    "type": "event",
    "id": "0c9f7768aa16003f976fcaccdf9f01a8",
    "time": "2026-10-01T00:48:39Z",
    "source": "aishub",
    "station": "aishub",
    "mmsi": 257083750,
    "msg_type": "PositionReport",
    "lat": 22.32691833333333,
    "lon": 119.99580666666667,
    "message": {
        "NavigationalStatus": 0,
        "Sog": 16.3,
        "Cog": 322.2,
        "TrueHeading": 319,
    },
    "synthesized": True,
}

REST_FEATURE = {
    "type": "Feature",
    "id": 416000000,
    "geometry": {"type": "Point", "coordinates": [120.3, 22.6]},
    "properties": {
        "mmsi": 416000000,
        "cog": 180.0,
        "sog": 8.1,
        "heading": 182,
        "nav_status": 0,
        "destination": "KAOHSIUNG",
        "name": "DEMO MARU",
        "type": 70,
        "seen": "2026-10-01T00:49:10Z",
        "source": "aishub",
    },
}

# AIS "not available" sentinel values that must normalize to None.
WS_SENTINELS = {
    "type": "event",
    "id": "sentinel-1",
    "time": "2026-10-01T00:50:00Z",
    "source": "aisstream",
    "mmsi": 111111111,
    "msg_type": "PositionReport",
    "lat": 23.0,
    "lon": 120.5,
    "message": {"Sog": 102.3, "Cog": 360.0, "TrueHeading": 511},
    "synthesized": False,
}


# --- Normalization ---------------------------------------------------------- #
def test_openwaters_ws_event_normalization() -> None:
    provider = OpenWatersProvider()
    parsed = provider.parse_frame(WS_POSITION)
    assert parsed.kind == "position"
    obs = parsed.observation
    assert obs.latitude == 22.32691833333333
    assert obs.longitude == 119.99580666666667
    assert obs.sog_knots == 16.3
    assert obs.cog_deg == 322.2
    assert obs.heading_deg == 319.0
    assert obs.nav_status == 0
    assert obs.source == "aishub"
    assert obs.synthesized is True
    assert obs.mmsi == 257083750  # internal only


def test_openwaters_welcome_is_ack() -> None:
    provider = OpenWatersProvider()
    parsed = provider.parse_frame(WS_WELCOME)
    assert parsed.kind == "ack"


def test_openwaters_rest_feature_normalization() -> None:
    provider = OpenWatersProvider()
    parsed = provider.parse_frame(REST_FEATURE)
    assert parsed.kind == "position"
    obs = parsed.observation
    assert obs.longitude == 120.3
    assert obs.latitude == 22.6
    assert obs.sog_knots == 8.1
    assert obs.cog_deg == 180.0
    assert obs.heading_deg == 182.0
    assert obs.vessel_type == 70
    assert obs.name == "DEMO MARU"
    assert obs.destination == "KAOHSIUNG"


def test_openwaters_ais_sentinels_become_none() -> None:
    provider = OpenWatersProvider()
    obs = provider.parse_frame(WS_SENTINELS).observation
    assert obs.sog_knots is None  # 102.3 sentinel
    assert obs.cog_deg is None  # 360.0 sentinel
    assert obs.heading_deg is None  # 511 sentinel


def test_subscription_message_uses_bbox() -> None:
    provider = OpenWatersProvider()
    msg = provider.subscription_message(TAIWAN_BBOX)
    assert msg["type"] == "subscribe"
    assert msg["snapshot"] is True
    assert msg["bbox"] == [[21.5, 118.0, 26.5, 123.5]]


def test_openwaters_requires_no_credentials() -> None:
    assert OpenWatersProvider().requires_credentials() is False


# --- Store: update, dedup, trajectory, stale, bbox -------------------------- #
def _obs(provider_id: str, lat: float, lon: float, *, age_s: float = 0.0, **kw) -> LiveVesselObservation:
    observed = utcnow() - timedelta(seconds=age_s)
    return LiveVesselObservation(
        provider_id=provider_id,
        latitude=lat,
        longitude=lon,
        observed_at=observed,
        received_at=utcnow(),
        source=kw.pop("source", "aishub"),
        **kw,
    )


def test_store_update_and_dedup() -> None:
    store = LiveVesselStore()
    store.update(_obs("v1", 22.0, 120.0))
    store.update(_obs("v1", 22.1, 120.1))  # same vessel moves
    store.update(_obs("v2", 23.0, 121.0))
    assert store.vessel_count() == 2  # deduped by provider_id
    latest = store.get_latest("v1")
    assert latest.latitude == 22.1  # kept the newer position


def test_store_trajectory_retention() -> None:
    store = LiveVesselStore()
    store.update(_obs("v1", 22.0, 120.0))
    store.update(_obs("v1", 22.2, 120.2))
    store.update(_obs("v1", 22.4, 120.4))
    track = store.get_trajectory("v1")
    assert track is not None
    assert len(track) == 3  # all three distinct positions retained


def test_store_ignores_strictly_older_fix() -> None:
    store = LiveVesselStore()
    store.update(_obs("v1", 22.5, 120.5, age_s=0))
    store.update(_obs("v1", 10.0, 10.0, age_s=600))  # much older frame
    assert store.get_latest("v1").latitude == 22.5


def test_store_stale_cleanup() -> None:
    store = LiveVesselStore(stale_after=timedelta(minutes=15))
    store.update(_obs("fresh", 22.0, 120.0, age_s=0))
    store.update(_obs("old", 23.0, 121.0, age_s=20 * 60))  # 20 min old
    removed = store.cleanup_stale()
    assert removed == 1
    assert store.get_latest("old") is None
    assert store.get_latest("fresh") is not None


def test_store_bbox_filter() -> None:
    store = LiveVesselStore()
    store.update(_obs("inside", 22.0, 120.0))
    store.update(_obs("outside", 0.0, 0.0))
    inside = store.snapshot(bbox=TAIWAN_BBOX)
    ids = {o.provider_id for o in inside}
    assert ids == {"inside"}


# --- Reconnect / health state ----------------------------------------------- #
def test_consumer_health_snapshot_shape() -> None:
    store = LiveVesselStore()
    consumer = AisIngestConsumer(OpenWatersProvider(), store)
    snap = consumer.health_snapshot()
    assert snap["provider"] == "open_waters"
    assert snap["connected"] is False
    assert snap["status"] == "offline"  # no vessels, not connected
    assert set(snap) >= {
        "status",
        "provider",
        "connected",
        "last_message_at",
        "message_age_seconds",
        "vessel_count",
    }


def test_consumer_degraded_when_disconnected_but_data_present() -> None:
    store = LiveVesselStore()
    store.update(_obs("v1", 22.0, 120.0))
    consumer = AisIngestConsumer(OpenWatersProvider(), store)
    # Simulate a prior successful connection then disconnect.
    consumer.health.reconnect_attempts = 2
    snap = consumer.health_snapshot()
    assert snap["status"] == "degraded"  # has cached data while reconnecting
    assert snap["vessel_count"] == 1
    assert snap["reconnect_attempts"] == 2


def test_consumer_handle_raw_updates_store() -> None:
    store = LiveVesselStore()
    consumer = AisIngestConsumer(OpenWatersProvider(), store)
    consumer._handle_raw(json.dumps(WS_POSITION))
    assert store.vessel_count() == 1
    # Ack frames do not create vessels.
    consumer._handle_raw(json.dumps(WS_WELCOME))
    assert store.vessel_count() == 1


# --- API endpoints ---------------------------------------------------------- #
def _client_with_vessel() -> TestClient:
    live_pkg.reset_live_state()
    store = live_pkg.get_store()
    store.update(
        LiveVesselObservation(
            provider_id="tw-ship-1",
            latitude=22.3,
            longitude=120.0,
            observed_at=utcnow(),
            received_at=utcnow(),
            source="aishub",
            sog_knots=16.3,
            cog_deg=322.2,
            heading_deg=319.0,
            vessel_type=83,
            name="CLIPPER ERIS",
            destination="TW MLI",
            synthesized=False,
            mmsi=257083750,
        )
    )
    store.update(
        LiveVesselObservation(
            provider_id="tw-ship-1",
            latitude=22.35,
            longitude=120.05,
            observed_at=utcnow(),
            received_at=utcnow(),
            source="aishub",
            mmsi=257083750,
        )
    )
    return TestClient(create_app())


def test_live_health_endpoint(monkeypatch) -> None:
    monkeypatch.setenv("SEAWATCH_LIVE_INGEST", "false")
    monkeypatch.setenv("SEAWATCH_AREA_SCAN_SIGNING_KEY", "health-signing-secret-at-least-32-bytes")
    monkeypatch.setenv("SEAWATCH_AREA_SCAN_AUTOAUTH_LOOPBACK", "true")
    client = _client_with_vessel()
    try:
        resp = client.get("/live/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["provider"] == "open_waters"
        assert body["vessel_count"] == 1
        assert "message_age_seconds" in body
        assert body["live_ingest_enabled"] is False
        assert body["area_scan_autoauth_loopback_enabled"] is True
        assert "health-signing-secret" not in resp.text
    finally:
        live_pkg.reset_live_state()


def test_live_vessels_geojson_and_integrity_fields() -> None:
    client = _client_with_vessel()
    try:
        resp = client.get("/live/vessels")
        assert resp.status_code == 200
        body = resp.json()
        assert body["type"] == "FeatureCollection"
        assert body["vessel_count"] == 1
        feature = body["features"][0]
        assert feature["geometry"]["type"] == "Point"
        props = feature["properties"]
        # Data integrity fields present on every vessel.
        assert "observed_at" in props
        assert "source" in props
        assert "data_age_seconds" in props
        assert "synthesized" in props
    finally:
        live_pkg.reset_live_state()


def test_live_vessels_bbox_filter() -> None:
    client = _client_with_vessel()
    try:
        # A bbox far from Taiwan returns no vessels.
        resp = client.get(
            "/live/vessels",
            params={"min_lat": 0, "min_lon": 0, "max_lat": 1, "max_lon": 1},
        )
        assert resp.status_code == 200
        assert resp.json()["vessel_count"] == 0
    finally:
        live_pkg.reset_live_state()


def test_live_track_endpoint_and_not_found() -> None:
    client = _client_with_vessel()
    try:
        public_id = client.get("/live/vessels").json()["features"][0]["id"]
        resp = client.get(f"/live/vessels/{public_id}/track")
        assert resp.status_code == 200
        body = resp.json()
        assert body["geometry"]["type"] == "LineString"
        assert body["properties"]["point_count"] >= 1

        missing = client.get("/live/vessels/does-not-exist/track")
        assert missing.status_code == 404
    finally:
        live_pkg.reset_live_state()


def test_live_vessels_never_exposes_identity() -> None:
    client = _client_with_vessel()
    try:
        response = client.get("/live/vessels")
        text = response.text.lower()
        public_id = response.json()["features"][0]["id"]
        track = client.get(f"/live/vessels/{public_id}/track").text.lower()
        for token in ("mmsi", "257083750", "imo", "callsign", "tw-ship-1"):
            assert token not in text
            assert token not in track
    finally:
        live_pkg.reset_live_state()


def test_live_endpoints_do_not_require_credentials(monkeypatch) -> None:
    # No AISSTREAM/DATALASTIC/OPENWATERS key set; endpoints still work (store read).
    monkeypatch.delenv("AISSTREAM_API_KEY", raising=False)
    client = _client_with_vessel()
    try:
        assert client.get("/live/health").status_code == 200
        assert client.get("/live/vessels").status_code == 200
    finally:
        live_pkg.reset_live_state()
