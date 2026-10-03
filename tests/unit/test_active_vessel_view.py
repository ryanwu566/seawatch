from __future__ import annotations

from datetime import datetime, timezone

from apps.api.seawatch.live.active_view import ActiveVesselView
from apps.api.seawatch.live.identity import VesselIdentityRegistry
from apps.api.seawatch.live.provider import BoundingBox
from apps.api.seawatch.live.resilience import (
    CoverageKind,
    DisplayState,
    EdgeInputKind,
    ObservationOrigin,
    OperatingMode,
    PowerMode,
    ResilienceStatus,
    SourceStatus,
)
from apps.api.seawatch.live.schema import LiveVesselObservation
from apps.api.seawatch.live.store import LiveVesselStore


def _status(mode: OperatingMode) -> ResilienceStatus:
    cloud_fresh = mode is OperatingMode.CLOUD_LIVE
    edge_fresh = mode in {OperatingMode.EDGE_LIVE, OperatingMode.EDGE_REPLAY}
    return ResilienceStatus(
        mode=mode,
        coverage=CoverageKind.CLOUD if cloud_fresh else CoverageKind.EDGE,
        simulated=mode is OperatingMode.EDGE_REPLAY,
        cloud=SourceStatus("cloud", cloud_fresh, 0.0, 1, cloud_fresh, None),
        edge=SourceStatus(
            "edge",
            edge_fresh,
            0.0,
            1,
            edge_fresh,
            EdgeInputKind.REPLAY
            if mode is OperatingMode.EDGE_REPLAY
            else EdgeInputKind.UDP,
        ),
        power_mode=PowerMode.EXTERNAL,
    )


def test_cloud_only_view_adds_opaque_identity_and_provenance() -> None:
    now = datetime(2026, 10, 1, tzinfo=timezone.utc)
    store = LiveVesselStore()
    store.update(
        LiveVesselObservation(
            provider_id="raw-cloud-key",
            latitude=22.3,
            longitude=120.1,
            observed_at=now,
            received_at=now,
            source="aishub",
            mmsi=416000001,
        )
    )
    view = ActiveVesselView(store, LiveVesselStore(), VesselIdentityRegistry("test-key"))

    public = view.snapshot(_status(OperatingMode.CLOUD_LIVE), now=now)

    assert len(public) == 1
    assert public[0].public_id.startswith("v_")
    assert public[0].public_id != "raw-cloud-key"
    assert public[0].origin is ObservationOrigin.CLOUD
    assert public[0].display_state is DisplayState.LIVE
    assert public[0].active_source is True
    assert public[0].coverage is CoverageKind.CLOUD

    track = view.track(public[0].public_id)
    assert track is not None
    assert track.public_id == public[0].public_id
    assert track.source_name == "cloud"
    assert [(point.longitude, point.latitude) for point in track.points] == [(120.1, 22.3)]


def test_cloud_only_view_returns_no_track_for_unknown_public_id() -> None:
    view = ActiveVesselView(
        LiveVesselStore(), LiveVesselStore(), VesselIdentityRegistry("test-key")
    )

    assert view.track("v_missing") is None


def test_failover_retains_prior_cloud_with_original_provenance_then_expires() -> None:
    now = datetime(2026, 10, 1, tzinfo=timezone.utc)
    clock = [10.0]
    cloud_store = LiveVesselStore()
    edge_store = LiveVesselStore()
    cloud_store.update(
        LiveVesselObservation(
            "cloud-key", 22.0, 120.0, now, now, "aishub", mmsi=416000001
        )
    )
    edge_store.update(
        LiveVesselObservation(
            "edge-key", 23.0, 121.0, now, now, "edge_ais", mmsi=416000002
        )
    )
    view = ActiveVesselView(
        cloud_store,
        edge_store,
        VesselIdentityRegistry("test-key"),
        monotonic=lambda: clock[0],
    )
    view.snapshot(_status(OperatingMode.CLOUD_LIVE), now=now)

    clock[0] = 20.0
    failed_over = view.snapshot(_status(OperatingMode.EDGE_LIVE), now=now)

    active = next(item for item in failed_over if item.active_source)
    cached = next(item for item in failed_over if not item.active_source)
    assert active.origin is ObservationOrigin.EDGE_RF
    assert active.display_state is DisplayState.LIVE
    assert cached.origin is ObservationOrigin.CLOUD
    assert cached.display_state is DisplayState.STALE
    assert cached.coverage is CoverageKind.CLOUD
    cached_track = view.track(cached.public_id)
    assert cached_track is not None
    assert cached_track.source_name == "cloud"

    clock[0] = 321.0
    assert [item.origin for item in view.snapshot(_status(OperatingMode.EDGE_LIVE))] == [
        ObservationOrigin.EDGE_RF
    ]
    assert view.track(cached.public_id) is None


def test_exact_mmsi_dedupes_but_tracks_follow_active_source() -> None:
    now = datetime(2026, 10, 1, tzinfo=timezone.utc)
    cloud_store = LiveVesselStore()
    edge_store = LiveVesselStore()
    for store, key, source, lat in (
        (cloud_store, "cloud-key", "aishub", 22.0),
        (edge_store, "edge-key", "edge_ais", 23.0),
    ):
        store.update(
            LiveVesselObservation(
                key, lat, 120.0, now, now, source, mmsi=416000001
            )
        )
    view = ActiveVesselView(
        cloud_store, edge_store, VesselIdentityRegistry("test-key")
    )
    view.snapshot(_status(OperatingMode.CLOUD_LIVE), now=now)

    edge_view = view.snapshot(_status(OperatingMode.EDGE_LIVE), now=now)

    assert len(edge_view) == 1
    assert edge_view[0].observation.latitude == 23.0
    track = view.track(edge_view[0].public_id)
    assert track is not None
    assert track.source_name == "edge"
    assert [point.latitude for point in track.points] == [23.0]


def test_uncertain_identities_do_not_merge_and_bbox_applies_after_selection() -> None:
    now = datetime(2026, 10, 1, tzinfo=timezone.utc)
    cloud_store = LiveVesselStore()
    edge_store = LiveVesselStore()
    cloud_store.update(
        LiveVesselObservation("same-looking", 22.0, 120.0, now, now, "aishub")
    )
    edge_store.update(
        LiveVesselObservation("same-looking", 25.0, 122.0, now, now, "edge_ais")
    )
    view = ActiveVesselView(
        cloud_store, edge_store, VesselIdentityRegistry("test-key")
    )
    cloud = view.snapshot(_status(OperatingMode.CLOUD_LIVE), now=now)
    edge = view.snapshot(
        _status(OperatingMode.EDGE_LIVE),
        bbox=BoundingBox(min_lat=24.0, min_lon=121.0, max_lat=26.0, max_lon=123.0),
        now=now,
    )

    assert len(edge) == 1
    assert edge[0].origin is ObservationOrigin.EDGE_RF
    assert edge[0].public_id != cloud[0].public_id


def test_no_source_returns_stale_cache_then_expires_and_cached_edge_track_stays_edge() -> None:
    now = datetime(2026, 10, 1, tzinfo=timezone.utc)
    clock = [1.0]
    edge_store = LiveVesselStore()
    edge_store.update(
        LiveVesselObservation(
            "edge-only", 23.0, 121.0, now, now, "edge_ais", mmsi=416000009
        )
    )
    view = ActiveVesselView(
        LiveVesselStore(),
        edge_store,
        VesselIdentityRegistry("test-key"),
        monotonic=lambda: clock[0],
    )
    active = view.snapshot(_status(OperatingMode.EDGE_LIVE), now=now)[0]

    clock[0] = 2.0
    cached = view.snapshot(_status(OperatingMode.NO_LIVE_SOURCE), now=now)
    track = view.track(active.public_id)

    assert len(cached) == 1
    assert cached[0].display_state is DisplayState.STALE
    assert cached[0].active_source is False
    assert track is not None
    assert track.source_name == "edge"

    clock[0] = 303.0
    assert view.snapshot(_status(OperatingMode.NO_LIVE_SOURCE), now=now) == []
    assert view.track(active.public_id) is None
