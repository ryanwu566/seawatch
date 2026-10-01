from __future__ import annotations

from datetime import datetime, timezone

from apps.api.seawatch.live.active_view import ActiveVesselView
from apps.api.seawatch.live.identity import VesselIdentityRegistry
from apps.api.seawatch.live.resilience import CoverageKind, DisplayState, ObservationOrigin
from apps.api.seawatch.live.schema import LiveVesselObservation
from apps.api.seawatch.live.store import LiveVesselStore


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
    view = ActiveVesselView(store, VesselIdentityRegistry("test-key"))

    public = view.snapshot(now=now)

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
    view = ActiveVesselView(LiveVesselStore(), VesselIdentityRegistry("test-key"))

    assert view.track("v_missing") is None
