"""Live Area Scan observations must carry what Detection reads: nav status, ship type, registry class and towing text."""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np

from apps.api.seawatch.detection import engine
from apps.api.seawatch.detection.context import DetectionContext
from apps.api.seawatch.detection.live_adapter import DetectionTrackAdapter, RollingTrackBuffer
from apps.api.seawatch.detection.territory import Territory
from apps.api.seawatch.live.provider_codes import nav_status_code, vessel_type_code
from apps.api.seawatch.live.schema import LiveVesselObservation


def test_navigation_status_text_maps_to_ais_codes():
    assert nav_status_code("Restricted manoeuvrability") == 3
    assert nav_status_code("Restricted maneuverability") == 3
    assert nav_status_code("Under way using engine") == 0
    assert nav_status_code("At anchor") == 1
    assert nav_status_code("Moored") == 5
    assert nav_status_code("Engaged in fishing") == 7
    assert nav_status_code("Not under command") == 2
    assert nav_status_code("something new") is None and nav_status_code(None) is None


def test_vessel_type_text_maps_to_ship_codes():
    assert vessel_type_code("Fishing") == 30
    assert vessel_type_code("Tug") == 52
    assert vessel_type_code("Cargo", "Bulk carrier") == 70
    assert vessel_type_code("Tanker") == 80
    assert vessel_type_code("Research", "Research/Survey Vessel") == 90
    assert vessel_type_code(None) is None


def _obs(minutes: int, **kw) -> LiveVesselObservation:
    t = datetime(2026, 10, 4, 0, 0, tzinfo=timezone.utc)
    base = dict(provider_id="p1", latitude=24.4, longitude=120.6, observed_at=t.replace(minute=minutes), received_at=t.replace(minute=minutes), source="datalastic",
                sog_knots=3.8, cog_deg=90.0, heading_deg=90.0, nav_status=3, vessel_type=90, name="TAN SUO TEST", destination="TOWING KEEP 3NM CPA",
                mmsi=413229999, vessel_subtype="Research vessel")
    base.update(kw)
    return LiveVesselObservation(**base)


def test_adapter_carries_towing_times_and_registry_class_into_the_track():
    buf = RollingTrackBuffer(clock=lambda: datetime(2026, 10, 4, 0, 30, tzinfo=timezone.utc))
    buf.update_many([_obs(1), _obs(5, longitude=120.61)])
    track = DetectionTrackAdapter().to_tracks(buf.snapshot())[0]
    assert track.extra["subtype"] == "Research vessel"
    assert len(track.extra["tow_t"]) == 2
    assert track.status is not None and int(track.status[0]) == 3


def test_one_towing_report_inside_taiwan_waters_is_raised_not_hidden():
    buf = RollingTrackBuffer(clock=lambda: datetime(2026, 10, 4, 0, 30, tzinfo=timezone.utc))
    buf.update_many([_obs(1)])
    tracks = DetectionTrackAdapter().to_tracks(buf.snapshot())
    ctx = DetectionContext([], [])
    ctx.territory = Territory.default()
    res = engine.analyze(tracks, ctx, density="sparse_live")
    assert res.n_analyzed == 1 and res.alerts and any(e.metrics.get("rule") == "R7" for e in res.events)


def test_plain_single_report_still_needs_history():
    buf = RollingTrackBuffer(clock=lambda: datetime(2026, 10, 4, 0, 30, tzinfo=timezone.utc))
    buf.update_many([_obs(1, name="PLAIN CARGO", destination="KAOHSIUNG", nav_status=0, vessel_type=70, vessel_subtype="Cargo", sog_knots=12.0)])
    tracks = DetectionTrackAdapter().to_tracks(buf.snapshot())
    ctx = DetectionContext([], [])
    ctx.territory = Territory.default()
    res = engine.analyze(tracks, ctx, density="sparse_live")
    assert res.n_analyzed == 0 and not res.alerts
