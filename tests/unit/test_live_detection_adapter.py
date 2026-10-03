"""Provider-independent live observation buffering and detection adaptation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np
import pytest

from apps.api.seawatch.live.schema import LiveVesselObservation


UTC = timezone.utc
BASE = datetime(2026, 10, 3, 0, 0, tzinfo=UTC)


@dataclass
class _Clock:
    now: datetime = BASE

    def __call__(self) -> datetime:
        return self.now


@dataclass
class _CountingClock:
    now: datetime = BASE
    calls: int = 0

    def __call__(self) -> datetime:
        self.calls += 1
        return self.now


def _obs(
    seconds: float = 0,
    *,
    provider_id: str = "provider-vessel-1",
    source: str = "open_waters",
    mmsi: Any = 416000001,
    latitude: float = 23.5,
    longitude: float = 121.0,
    **changes: Any,
) -> LiveVesselObservation:
    values: dict[str, Any] = {
        "provider_id": provider_id,
        "latitude": latitude,
        "longitude": longitude,
        "observed_at": BASE + timedelta(seconds=seconds),
        "received_at": BASE + timedelta(seconds=seconds + 1),
        "source": source,
        "mmsi": mmsi,
    }
    values.update(changes)
    return LiveVesselObservation(**values)


def _buffer_type():
    from apps.api.seawatch.detection.live_adapter import RollingTrackBuffer

    return RollingTrackBuffer


def _adapter_type():
    from apps.api.seawatch.detection.live_adapter import DetectionTrackAdapter

    return DetectionTrackAdapter


def _analyzer_type():
    from apps.api.seawatch.detection.live_adapter import LiveDetectionAnalyzer

    return LiveDetectionAnalyzer


@pytest.mark.parametrize("latitude", [-90.0001, 90.0001])
def test_buffer_rejects_latitude_outside_wgs84(latitude: float) -> None:
    buffer = _buffer_type()(clock=_Clock())

    with pytest.raises(ValueError, match="latitude"):
        buffer.update(_obs(latitude=latitude))


@pytest.mark.parametrize("longitude", [-180.0001, 180.0001])
def test_buffer_rejects_longitude_outside_wgs84(longitude: float) -> None:
    buffer = _buffer_type()(clock=_Clock())

    with pytest.raises(ValueError, match="longitude"):
        buffer.update(_obs(longitude=longitude))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("latitude", float("nan")),
        ("latitude", float("inf")),
        ("latitude", float("-inf")),
        ("longitude", float("nan")),
        ("longitude", float("inf")),
        ("longitude", float("-inf")),
    ],
)
def test_buffer_rejects_non_finite_positions(field: str, value: float) -> None:
    buffer = _buffer_type()(clock=_Clock())

    with pytest.raises(ValueError, match=field):
        buffer.update(_obs(**{field: value}))


def test_buffer_rejects_explicit_zero_stale_window() -> None:
    with pytest.raises(ValueError, match="stale_after"):
        _buffer_type()(stale_after=timedelta(0), clock=_Clock())


def test_buffer_suppresses_exact_duplicate_observation() -> None:
    buffer = _buffer_type()(clock=_Clock())
    observation = _obs()

    assert buffer.update(observation) is True
    assert buffer.update(observation) is False
    assert buffer.vessel_count() == 1
    assert buffer.point_count() == 1


def test_four_distinct_provider_polls_preserve_the_exact_trajectory() -> None:
    buffer = _buffer_type()(clock=_Clock(BASE + timedelta(minutes=10)))
    observations = [
        _obs(0, latitude=23.50, longitude=121.00),
        _obs(60, latitude=23.51, longitude=121.01),
        _obs(120, latitude=23.52, longitude=121.02),
        _obs(180, latitude=23.53, longitude=121.03),
    ]

    assert buffer.update_many(observations) == 4

    track = _adapter_type()().to_track(buffer.snapshot()[0])
    assert track is not None
    assert track.t.tolist() == [item.observed_at.timestamp() for item in observations]
    assert track.lat.tolist() == [23.50, 23.51, 23.52, 23.53]
    assert track.lon.tolist() == [121.00, 121.01, 121.02, 121.03]


def test_same_coordinates_at_different_timestamps_remain_distinct() -> None:
    buffer = _buffer_type()(clock=_Clock(BASE + timedelta(minutes=10)))

    assert buffer.update_many([_obs(0), _obs(60), _obs(120)]) == 3

    retained = buffer.snapshot()[0].observations
    assert [item.observed_at for item in retained] == [
        BASE,
        BASE + timedelta(seconds=60),
        BASE + timedelta(seconds=120),
    ]


def test_buffer_sorts_out_of_order_observations_chronologically() -> None:
    buffer = _buffer_type()(clock=_Clock(BASE + timedelta(minutes=10)))
    buffer.update_many([_obs(300), _obs(0), _obs(120)])

    tracks = buffer.snapshot()

    assert len(tracks) == 1
    assert [o.observed_at for o in tracks[0].observations] == [
        BASE,
        BASE + timedelta(seconds=120),
        BASE + timedelta(seconds=300),
    ]


def test_valid_mmsi_groups_the_same_vessel_across_sources() -> None:
    buffer = _buffer_type()(clock=_Clock(BASE + timedelta(minutes=10)))

    buffer.update(_obs(0, source="open_waters", provider_id="ow-1"))
    buffer.update(_obs(60, source="edge_ais", provider_id="edge-9"))

    tracks = buffer.snapshot()
    assert len(tracks) == 1
    assert tracks[0].identity.mmsi == "416000001"
    assert {o.source for o in tracks[0].observations} == {"open_waters", "edge_ais"}


def test_shared_mmsi_across_sources_preserves_chronological_trajectory() -> None:
    buffer = _buffer_type()(clock=_Clock(BASE + timedelta(minutes=10)))
    observations = [
        _obs(120, source="source-a", provider_id="a-1", latitude=23.52),
        _obs(0, source="source-b", provider_id="b-1", latitude=23.50),
        _obs(60, source="source-a", provider_id="a-1", latitude=23.51),
    ]

    assert buffer.update_many(observations) == 3

    track = _adapter_type()().to_track(buffer.snapshot()[0])
    assert track is not None
    assert track.t.tolist() == [
        BASE.timestamp(),
        (BASE + timedelta(seconds=60)).timestamp(),
        (BASE + timedelta(seconds=120)).timestamp(),
    ]
    assert track.lat.tolist() == [23.50, 23.51, 23.52]
    assert track.extra is not None
    assert track.extra["point_sources"] == ("source-b", "source-a", "source-a")


def test_fractional_mmsi_is_not_truncated_or_used_cross_source() -> None:
    buffer = _buffer_type()(clock=_Clock(BASE + timedelta(minutes=10)))

    buffer.update(_obs(0, source="source-a", provider_id="a-1", mmsi=416000001.5))
    buffer.update(_obs(60, source="source-b", provider_id="b-1", mmsi=416000001.5))

    tracks = buffer.snapshot()
    assert len(tracks) == 2
    assert all(track.identity.mmsi is None for track in tracks)


def test_buffer_keeps_only_newest_points_at_point_cap() -> None:
    buffer = _buffer_type()(max_points_per_vessel=2, clock=_Clock(BASE + timedelta(minutes=10)))

    buffer.update_many([_obs(0), _obs(60), _obs(120)])

    retained = buffer.snapshot()[0].observations
    assert [o.observed_at for o in retained] == [BASE + timedelta(seconds=60), BASE + timedelta(seconds=120)]


def test_retention_removes_points_older_than_the_time_window() -> None:
    clock = _Clock(BASE)
    buffer = _buffer_type()(retention=timedelta(minutes=10), stale_after=timedelta(hours=1), clock=clock)
    buffer.update(_obs(0))

    clock.now = BASE + timedelta(minutes=20)
    buffer.update(_obs(20 * 60))

    retained = buffer.snapshot()[0].observations
    assert [o.observed_at for o in retained] == [BASE + timedelta(minutes=20)]


def test_initial_ingest_rejects_stale_observation_but_accepts_fresh_one() -> None:
    clock = _Clock(BASE + timedelta(minutes=11))
    buffer = _buffer_type()(
        retention=timedelta(hours=1),
        stale_after=timedelta(minutes=10),
        clock=clock,
    )

    assert buffer.update(_obs(0)) is False
    assert buffer.update(_obs(120)) is True
    assert buffer.point_count() == 1


def test_retention_cutoff_is_inclusive_and_only_older_observations_are_rejected() -> None:
    buffer = _buffer_type()(
        retention=timedelta(minutes=10),
        stale_after=timedelta(hours=1),
        clock=_Clock(BASE + timedelta(minutes=10)),
    )

    assert buffer.update(_obs(0, mmsi=416000001)) is True
    assert buffer.update(_obs(-1, mmsi=416000002, provider_id="older")) is False


def test_stale_cutoff_is_inclusive_and_only_older_observations_are_rejected() -> None:
    buffer = _buffer_type()(
        retention=timedelta(hours=1),
        stale_after=timedelta(minutes=10),
        clock=_Clock(BASE + timedelta(minutes=10)),
    )

    assert buffer.update(_obs(0, mmsi=416000001)) is True
    assert buffer.update(_obs(-1, mmsi=416000002, provider_id="older")) is False


def test_snapshot_prunes_vessel_after_stale_window_without_a_mutation() -> None:
    clock = _Clock(BASE)
    buffer = _buffer_type()(
        retention=timedelta(hours=1),
        stale_after=timedelta(minutes=10),
        clock=clock,
    )
    assert buffer.update(_obs()) is True

    clock.now = BASE + timedelta(minutes=11)

    assert buffer.snapshot() == ()


def test_count_reads_prune_expired_state_under_the_injected_clock() -> None:
    clock = _Clock(BASE)
    buffer = _buffer_type()(
        retention=timedelta(hours=1),
        stale_after=timedelta(minutes=10),
        clock=clock,
    )
    buffer.update(_obs())
    clock.now = BASE + timedelta(minutes=11)

    assert buffer.vessel_count() == 0
    assert buffer.point_count() == 0


def test_expired_replay_is_rejected_and_fresh_observation_recreates_track() -> None:
    clock = _Clock(BASE)
    buffer = _buffer_type()(
        retention=timedelta(hours=1),
        stale_after=timedelta(minutes=10),
        clock=clock,
    )
    expired = _obs(name="OLD NAME", destination="OLD PORT")
    assert buffer.update(expired) is True

    clock.now = BASE + timedelta(minutes=11)
    assert buffer.snapshot() == ()
    assert buffer.update(expired) is False

    fresh = _obs(
        11 * 60,
        source="edge_ais",
        provider_id="fresh-provider-id",
        name="NEW NAME",
        destination=None,
    )
    assert buffer.update(fresh) is True

    track = _adapter_type()().to_track(buffer.snapshot()[0])
    assert track is not None
    assert track.name == "NEW NAME"
    assert track.extra is not None
    assert track.extra["sources"] == ("edge_ais",)
    assert "destination" not in track.extra


def test_stale_vessel_eviction_uses_the_injected_clock() -> None:
    clock = _Clock(BASE)
    buffer = _buffer_type()(stale_after=timedelta(minutes=30), clock=clock)
    buffer.update(_obs(0, mmsi=416000001, provider_id="old"))
    buffer.update(_obs(20 * 60, mmsi=416000002, provider_id="recent"))

    clock.now = BASE + timedelta(minutes=40)

    assert buffer.evict_stale() == 1
    assert [track.identity.mmsi for track in buffer.snapshot()] == ["416000002"]


def test_vessel_cap_evicts_the_least_recent_vessel() -> None:
    buffer = _buffer_type()(max_vessels=2, clock=_Clock(BASE + timedelta(minutes=10)))
    buffer.update(_obs(0, mmsi=416000001, provider_id="one"))
    buffer.update(_obs(60, mmsi=416000002, provider_id="two"))
    buffer.update(_obs(120, mmsi=416000003, provider_id="three"))

    assert [track.identity.mmsi for track in buffer.snapshot()] == ["416000002", "416000003"]


def test_vessel_cap_is_independent_of_out_of_order_batch_permutation() -> None:
    observations = [
        _obs(0, mmsi=416000001, provider_id="one"),
        _obs(60, mmsi=416000002, provider_id="two"),
        _obs(120, mmsi=416000001, provider_id="one"),
    ]
    results = []
    for batch in (observations, [observations[0], observations[2], observations[1]]):
        buffer = _buffer_type()(max_vessels=1, clock=_Clock(BASE + timedelta(minutes=10)))
        accepted = buffer.update_many(batch)
        results.append((accepted, buffer.snapshot()))

    assert [accepted for accepted, _ in results] == [2, 2]
    assert [track.identity.mmsi for track in results[0][1]] == ["416000001"]
    assert [item.observed_at for item in results[0][1][0].observations] == [
        BASE,
        BASE + timedelta(seconds=120),
    ]
    assert results[0] == results[1]


def test_vessel_cap_tie_break_is_independent_of_batch_order() -> None:
    first = _obs(60, mmsi=416000001, provider_id="one")
    second = _obs(60, mmsi=416000002, provider_id="two")
    retained = []
    for batch in ([first, second], [second, first]):
        buffer = _buffer_type()(max_vessels=1, clock=_Clock(BASE + timedelta(minutes=10)))
        buffer.update_many(batch)
        retained.append([track.identity.mmsi for track in buffer.snapshot()])

    assert retained == [["416000002"], ["416000002"]]


def test_oversized_capacity_batch_retains_deterministic_newest_set() -> None:
    observations = [
        _obs(second, mmsi=416000000 + second, provider_id=str(second))
        for second in range(1, 21)
    ]
    retained = []
    for batch in (observations, list(reversed(observations))):
        buffer = _buffer_type()(max_vessels=5, clock=_Clock(BASE + timedelta(minutes=10)))
        assert buffer.update_many(batch) == 5
        retained.append([track.identity.mmsi for track in buffer.snapshot()])

    assert retained == [
        ["416000016", "416000017", "416000018", "416000019", "416000020"],
        ["416000016", "416000017", "416000018", "416000019", "416000020"],
    ]


def test_capacity_selection_combines_existing_vessels_with_oversized_batch() -> None:
    buffer = _buffer_type()(max_vessels=5, clock=_Clock(BASE + timedelta(minutes=10)))
    assert buffer.update(_obs(300, mmsi=416000050, provider_id="existing")) is True

    accepted = buffer.update_many(
        _obs(second, mmsi=416000000 + second, provider_id=str(second))
        for second in range(1, 21)
    )

    assert accepted == 4
    assert [track.identity.mmsi for track in buffer.snapshot()] == [
        "416000017",
        "416000018",
        "416000019",
        "416000020",
        "416000050",
    ]


def test_stale_vessels_are_pruned_before_capacity_selection() -> None:
    clock = _Clock(BASE)
    buffer = _buffer_type()(
        max_vessels=2,
        retention=timedelta(hours=1),
        stale_after=timedelta(minutes=10),
        clock=clock,
    )
    buffer.update_many(
        [
            _obs(0, mmsi=416000001, provider_id="stale-one"),
            _obs(0, mmsi=416000002, provider_id="stale-two"),
        ]
    )
    clock.now = BASE + timedelta(minutes=11)

    accepted = buffer.update_many(
        [
            _obs(11 * 60, mmsi=416000003, provider_id="fresh-three"),
            _obs(11 * 60, mmsi=416000004, provider_id="fresh-four"),
        ]
    )

    assert accepted == 2
    assert [track.identity.mmsi for track in buffer.snapshot()] == ["416000003", "416000004"]


def test_capacity_selection_evaluates_each_vessel_order_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from apps.api.seawatch.detection.live_adapter import LiveTrackIdentity

    evaluations = 0
    original_sort_key = LiveTrackIdentity.sort_key

    def counted_sort_key(identity: Any) -> tuple[str, str, str]:
        nonlocal evaluations
        evaluations += 1
        return original_sort_key(identity)

    monkeypatch.setattr(LiveTrackIdentity, "sort_key", counted_sort_key)
    buffer = _buffer_type()(max_vessels=10, clock=_Clock(BASE + timedelta(minutes=10)))
    observations = [
        _obs(second, mmsi=416000000 + second, provider_id=str(second))
        for second in range(1, 201)
    ]

    assert buffer.update_many(observations) == 10
    assert buffer.vessel_count() == 10
    assert evaluations == 200


def test_vessel_cap_is_restored_when_a_batch_contains_a_malformed_fix() -> None:
    buffer = _buffer_type()(max_vessels=1, clock=_Clock(BASE + timedelta(minutes=10)))

    with pytest.raises(ValueError, match="latitude"):
        buffer.update_many(
            [
                _obs(0, mmsi=416000001, provider_id="one"),
                _obs(60, mmsi=416000002, provider_id="two"),
                _obs(120, mmsi=416000003, provider_id="bad", latitude=float("nan")),
            ]
        )

    assert buffer.vessel_count() == 1


def test_total_buffer_memory_is_bounded_by_vessel_and_point_caps() -> None:
    buffer = _buffer_type()(max_vessels=3, max_points_per_vessel=2, clock=_Clock(BASE + timedelta(hours=1)))
    observations = [
        _obs(vessel * 300 + point * 60, mmsi=416000000 + vessel, provider_id=str(vessel))
        for vessel in range(1, 6)
        for point in range(5)
    ]

    buffer.update_many(observations)

    assert buffer.vessel_count() == 3
    assert buffer.point_count() == 6


def test_batch_update_uses_one_consistent_maintenance_time() -> None:
    clock = _CountingClock(BASE + timedelta(hours=1))
    buffer = _buffer_type()(clock=clock)

    buffer.update_many([_obs(point * 60) for point in range(8)])

    assert clock.calls == 1


def test_oversized_batch_is_rejected_before_buffer_mutation() -> None:
    clock = _CountingClock(BASE + timedelta(hours=1))
    buffer = _buffer_type()(max_batch_observations=2, clock=clock)

    with pytest.raises(ValueError, match="max_batch_observations"):
        buffer.update_many(_obs(point * 60) for point in range(3))

    assert clock.calls == 0
    assert buffer.vessel_count() == 0
    assert buffer.point_count() == 0


def test_adapter_maps_supported_live_fields_to_detection_track() -> None:
    buffer = _buffer_type()(clock=_Clock(BASE + timedelta(minutes=10)))
    buffer.update(
        _obs(
            0,
            source="open_waters",
            provider_id="ow-1",
            latitude=23.5,
            longitude=121.0,
            sog_knots=4.5,
            cog_deg=90.0,
            heading_deg=88.0,
            nav_status=0,
            vessel_type=70,
            name="SEA TEST",
            destination="KAOHSIUNG",
        )
    )
    buffer.update(
        _obs(
            60,
            source="edge_ais",
            provider_id="edge-1",
            latitude=23.6,
            longitude=121.1,
            sog_knots=5.5,
            cog_deg=100.0,
            heading_deg=99.0,
            nav_status=3,
            vessel_type=70,
            name="SEA TEST",
            destination="KAOHSIUNG",
            synthesized=True,
        )
    )

    track = _adapter_type()().to_track(buffer.snapshot()[0])

    assert track is not None
    assert track.mmsi == "416000001"
    assert track.name == "SEA TEST"
    assert track.ship_type == "cargo"
    assert track.flag == ""
    assert track.imo == ""
    assert track.t.tolist() == [BASE.timestamp(), (BASE + timedelta(seconds=60)).timestamp()]
    assert track.lat.tolist() == [23.5, 23.6]
    assert track.lon.tolist() == [121.0, 121.1]
    assert track.sog.tolist() == [4.5, 5.5]
    assert track.cog.tolist() == [90.0, 100.0]
    assert track.status is not None and track.status.tolist() == [0, 3]
    assert track.extra == {
        "destination": "KAOHSIUNG",
        "sources": ("edge_ais", "open_waters"),
        "point_sources": ("open_waters", "edge_ais"),
        "heading_deg": (88.0, 99.0),
        "synthesized": (False, True),
    }


def test_adapter_uses_explicit_missing_representations() -> None:
    buffer = _buffer_type()(clock=_Clock(BASE + timedelta(minutes=10)))
    buffer.update_many([_obs(0), _obs(60)])

    track = _adapter_type()().to_track(buffer.snapshot()[0])

    assert track is not None
    assert np.isnan(track.sog).all()
    assert np.isnan(track.cog).all()
    assert track.status is None
    assert track.extra is not None
    assert track.extra["heading_deg"] == (None, None)
    assert "destination" not in track.extra


def test_adapter_uses_minus_one_for_missing_status_in_partial_array() -> None:
    buffer = _buffer_type()(clock=_Clock(BASE + timedelta(minutes=10)))
    buffer.update_many([_obs(0), _obs(60, nav_status=5)])

    track = _adapter_type()().to_track(buffer.snapshot()[0])

    assert track is not None
    assert track.status is not None and track.status.tolist() == [-1, 5]


def test_adapter_treats_non_finite_optional_numbers_as_missing() -> None:
    buffer = _buffer_type()(clock=_Clock(BASE + timedelta(minutes=10)))
    buffer.update(_obs(sog_knots=float("inf"), cog_deg=float("nan"), heading_deg=float("-inf")))

    track = _adapter_type()().to_track(buffer.snapshot()[0])

    assert track is not None
    assert np.isnan(track.sog[0])
    assert np.isnan(track.cog[0])
    assert track.extra is not None and track.extra["heading_deg"] == (None,)


def test_adapter_does_not_fabricate_mmsi_for_source_scoped_identity() -> None:
    buffer = _buffer_type()(clock=_Clock(BASE + timedelta(minutes=10)))
    buffer.update(_obs(mmsi=None, source="edge_ais", provider_id="edge-without-mmsi"))
    adapter = _adapter_type()()

    assert adapter.to_track(buffer.snapshot()[0]) is None
    assert adapter.to_tracks(buffer.snapshot()) == []


def test_adapter_resolves_same_timestamp_conflicts_deterministically() -> None:
    first = _obs(0, source="source-a", provider_id="a", latitude=23.0)
    second = _obs(0, source="source-b", provider_id="b", latitude=24.0)
    tracks = []
    for observations in ([first, second], [second, first]):
        buffer = _buffer_type()(clock=_Clock(BASE + timedelta(minutes=10)))
        buffer.update_many(observations)
        track = _adapter_type()().to_track(buffer.snapshot()[0])
        assert track is not None
        tracks.append(track)

    assert tracks[0].t.tolist() == tracks[1].t.tolist() == [BASE.timestamp()]
    assert tracks[0].lat.tolist() == tracks[1].lat.tolist() == [24.0]
    assert tracks[0].extra is not None
    assert tracks[0].extra["point_sources"] == ("source-b",)


def test_same_timestamp_optional_field_conflicts_are_totally_ordered() -> None:
    buffer = _buffer_type()(clock=_Clock(BASE + timedelta(minutes=10)))
    buffer.update(_obs(0, nav_status=None, name=None))
    buffer.update(_obs(0, nav_status=5, name="WITH STATIC DATA"))

    track = _adapter_type()().to_track(buffer.snapshot()[0])

    assert track is not None
    assert track.t.tolist() == [BASE.timestamp()]
    assert track.status is not None and track.status.tolist() == [5]


def test_adapter_delegates_to_engine_eligibility_matrix() -> None:
    buffer = _buffer_type()(clock=_Clock(BASE + timedelta(minutes=10)))
    buffer.update_many([_obs(0), _obs(60)])
    adapter = _adapter_type()()
    track = adapter.to_track(buffer.snapshot()[0])
    assert track is not None

    eligibility = adapter.eligibility(track, density="sparse_live")

    assert eligibility["zone_entry"] is None
    assert eligibility["position_jump"] == "insufficient_data"
    assert eligibility["loitering"] == "not_applicable"
    assert eligibility["route_deviation"] == "not_applicable"


def test_one_live_observation_cannot_create_trajectory_event_or_alert() -> None:
    from apps.api.seawatch.detection.context import DetectionContext

    analyzer = _analyzer_type()(
        DetectionContext([], []),
        density="sparse_live",
        buffer=_buffer_type()(clock=_Clock(BASE + timedelta(minutes=10))),
    )

    result = analyzer.update([_obs(0)])

    assert result.events == []
    assert result.alerts == []
    assert result.n_tracks == 1
    assert result.n_analyzed == 0
    assert any(item.reason == "insufficient_data" for item in result.skipped)


def test_short_live_history_safely_returns_no_event() -> None:
    from apps.api.seawatch.detection.context import DetectionContext

    analyzer = _analyzer_type()(
        DetectionContext([], []),
        density="sparse_live",
        buffer=_buffer_type()(clock=_Clock(BASE + timedelta(minutes=10))),
    )

    result = analyzer.update([_obs(0), _obs(60, latitude=23.5001, longitude=121.0001)])

    assert result.events == []
    assert result.alerts == []
    assert result.n_tracks == 1


def test_qualifying_live_track_produces_existing_event_and_fused_alert() -> None:
    from apps.api.seawatch.detection.alerts import Alert
    from apps.api.seawatch.detection.config import DetectionConfig
    from apps.api.seawatch.detection.context import DetectionContext
    from apps.api.seawatch.detection.models import Event

    analyzer = _analyzer_type()(
        DetectionContext([], []),
        density="sparse_live",
        config=DetectionConfig(alert_min_risk=0),
        buffer=_buffer_type()(clock=_Clock(BASE + timedelta(hours=1))),
    )
    observations = [
        _obs(0, latitude=23.0, longitude=121.0, sog_knots=5.0, name="JUMPER"),
        _obs(300, latitude=23.01, longitude=121.01, sog_knots=5.0, name="JUMPER"),
        _obs(600, latitude=25.0, longitude=125.0, sog_knots=5.0, name="JUMPER"),
        _obs(900, latitude=23.02, longitude=121.02, sog_knots=5.0, name="JUMPER"),
    ]

    result = analyzer.update(observations)

    event = next(item for item in result.events if item.kind == "position_jump")
    assert isinstance(event, Event)
    assert any(isinstance(alert, Alert) and event in alert.events for alert in result.alerts)


def test_multiple_live_vessels_are_analyzed_together_for_rendezvous() -> None:
    from apps.api.seawatch.detection.config import DetectionConfig
    from apps.api.seawatch.detection.context import DetectionContext

    analyzer = _analyzer_type()(
        DetectionContext([], []),
        density="message_level",
        config=DetectionConfig(rendezvous_min_minutes=15, alert_min_risk=0),
        buffer=_buffer_type()(clock=_Clock(BASE + timedelta(hours=2))),
    )
    observations = []
    for point in range(10):
        observations.extend(
            [
                _obs(
                    point * 300,
                    mmsi=416000001,
                    provider_id="vessel-a",
                    latitude=23.0 + point * 0.00001,
                    longitude=121.0,
                    sog_knots=1.0,
                    vessel_type=80,
                    name="TANKER A",
                ),
                _obs(
                    point * 300,
                    mmsi=416000002,
                    provider_id="vessel-b",
                    latitude=23.001 + point * 0.00001,
                    longitude=121.0,
                    sog_knots=1.0,
                    vessel_type=70,
                    name="CARGO B",
                ),
            ]
        )

    result = analyzer.update(observations)

    rendezvous = [event for event in result.events if event.kind == "rendezvous"]
    assert result.n_tracks == 2
    assert rendezvous
    assert set(rendezvous[0].mmsis) == {"416000001", "416000002"}


def test_analyzer_reuses_context_and_calls_engine_once_per_analysis(monkeypatch: pytest.MonkeyPatch) -> None:
    from apps.api.seawatch.detection import live_adapter
    from apps.api.seawatch.detection.context import DetectionContext
    from apps.api.seawatch.detection.engine import AnalysisResult

    context = DetectionContext([], [])
    calls: list[tuple[list[Any], Any]] = []

    def fake_analyze(tracks: list[Any], supplied_context: Any, **kwargs: Any) -> AnalysisResult:
        calls.append((tracks, supplied_context))
        return AnalysisResult([], [], n_tracks=len(tracks), n_analyzed=len(tracks), density=kwargs["density"])

    monkeypatch.setattr(live_adapter.engine, "analyze", fake_analyze)
    analyzer = _analyzer_type()(
        context,
        buffer=_buffer_type()(clock=_Clock(BASE + timedelta(minutes=10))),
    )

    analyzer.update([_obs(0, mmsi=416000001), _obs(0, mmsi=416000002, provider_id="two")])
    analyzer.update([_obs(60, mmsi=416000001), _obs(60, mmsi=416000002, provider_id="two")])

    assert len(calls) == 2
    assert all(supplied is context for _, supplied in calls)
    assert all(len(tracks) == 2 for tracks, _ in calls)


def test_analyzer_read_paths_do_not_expose_expired_track() -> None:
    from apps.api.seawatch.detection.context import DetectionContext

    clock = _Clock(BASE)
    analyzer = _analyzer_type()(
        DetectionContext([], []),
        density="sparse_live",
        buffer=_buffer_type()(
            retention=timedelta(hours=1),
            stale_after=timedelta(minutes=10),
            clock=clock,
        ),
    )
    assert analyzer.ingest([_obs()]) == 1
    clock.now = BASE + timedelta(minutes=11)

    assert analyzer.tracks() == []
    result = analyzer.analyze()
    assert result.n_tracks == 0
    assert result.events == []
    assert result.alerts == []


def test_analyzer_explicit_as_of_controls_expiry_instead_of_wall_clock() -> None:
    from apps.api.seawatch.detection.context import DetectionContext

    clock = _Clock(BASE)
    analyzer = _analyzer_type()(
        DetectionContext([], []),
        density="sparse_live",
        buffer=_buffer_type()(
            retention=timedelta(hours=1),
            stale_after=timedelta(minutes=10),
            clock=clock,
        ),
    )
    analyzer.ingest([_obs()])
    clock.now = BASE + timedelta(hours=2)

    historical = analyzer.analyze(as_of=(BASE + timedelta(minutes=5)).timestamp())

    assert historical.n_tracks == 1


def test_analyzer_update_uses_explicit_as_of_for_ingest_and_analysis() -> None:
    from apps.api.seawatch.detection.context import DetectionContext

    analyzer = _analyzer_type()(
        DetectionContext([], []),
        density="sparse_live",
        buffer=_buffer_type()(
            retention=timedelta(hours=1),
            stale_after=timedelta(minutes=10),
            clock=_Clock(BASE + timedelta(hours=2)),
        ),
    )

    result = analyzer.update(
        [_obs()],
        as_of=(BASE + timedelta(minutes=5)).timestamp(),
    )

    assert result.n_tracks == 1


def test_analyzer_explicit_as_of_excludes_track_stale_at_that_time() -> None:
    from apps.api.seawatch.detection.context import DetectionContext

    analyzer = _analyzer_type()(
        DetectionContext([], []),
        density="sparse_live",
        buffer=_buffer_type()(
            retention=timedelta(hours=1),
            stale_after=timedelta(minutes=10),
            clock=_Clock(BASE),
        ),
    )
    analyzer.ingest([_obs()])

    result = analyzer.analyze(as_of=(BASE + timedelta(minutes=11)).timestamp())

    assert result.n_tracks == 0


def test_historical_as_of_reads_are_independent_of_query_order() -> None:
    from apps.api.seawatch.detection.context import DetectionContext

    analyzer = _analyzer_type()(
        DetectionContext([], []),
        density="sparse_live",
        buffer=_buffer_type()(
            retention=timedelta(hours=1),
            stale_after=timedelta(hours=1),
            clock=_Clock(BASE),
        ),
    )
    analyzer.ingest([_obs()])

    expired = analyzer.analyze(as_of=(BASE + timedelta(hours=2)).timestamp())
    still_valid = analyzer.analyze(as_of=(BASE + timedelta(minutes=5)).timestamp())

    assert expired.n_tracks == 0
    assert still_valid.n_tracks == 1


def test_as_of_excludes_future_points_and_static_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    from apps.api.seawatch.detection import live_adapter
    from apps.api.seawatch.detection.context import DetectionContext
    from apps.api.seawatch.detection.engine import AnalysisResult

    captured: list[Any] = []

    def fake_analyze(tracks: list[Any], context: Any, **kwargs: Any) -> AnalysisResult:
        captured.extend(tracks)
        return AnalysisResult([], [], n_tracks=len(tracks), density=kwargs["density"])

    monkeypatch.setattr(live_adapter.engine, "analyze", fake_analyze)
    analyzer = _analyzer_type()(
        DetectionContext([], []),
        buffer=_buffer_type()(clock=_Clock(BASE + timedelta(minutes=10))),
    )
    analyzer.ingest(
        [
            _obs(0, name="PAST NAME", destination="PORT", vessel_type=70, heading_deg=10.0),
            _obs(60, name="PAST NAME", destination="PORT", vessel_type=70, heading_deg=11.0),
            _obs(120, name="FUTURE NAME", destination="CABLE SURVEY", vessel_type=80, heading_deg=99.0),
        ]
    )

    analyzer.analyze(as_of=(BASE + timedelta(seconds=60)).timestamp())

    assert len(captured) == 1
    track = captured[0]
    assert track.name == "PAST NAME"
    assert track.ship_type == "cargo"
    assert track.extra is not None
    assert track.extra["destination"] == "PORT"
    assert track.extra["heading_deg"] == (10.0, 11.0)
    assert len(track.extra["point_sources"]) == len(track) == 2


def test_analyzer_does_not_fabricate_ml_when_no_model_is_supplied() -> None:
    from apps.api.seawatch.detection.config import DetectionConfig
    from apps.api.seawatch.detection.context import DetectionContext

    analyzer = _analyzer_type()(
        DetectionContext([], []),
        density="sparse_live",
        config=DetectionConfig(alert_min_risk=0),
        buffer=_buffer_type()(clock=_Clock(BASE + timedelta(hours=1))),
    )

    result = analyzer.update(
        [
            _obs(0, latitude=23.0, longitude=121.0, sog_knots=5.0),
            _obs(300, latitude=23.01, longitude=121.01, sog_knots=5.0),
            _obs(600, latitude=25.0, longitude=125.0, sog_knots=5.0),
            _obs(900, latitude=23.02, longitude=121.02, sog_knots=5.0),
        ]
    )

    assert result.alerts
    assert all(alert.ml is None for alert in result.alerts)


def test_analyzer_operates_with_network_connections_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    import socket

    from apps.api.seawatch.detection.context import DetectionContext

    def fail_network(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("live detection adapter attempted network access")

    monkeypatch.setattr(socket, "create_connection", fail_network)
    monkeypatch.setattr(socket.socket, "connect", fail_network)
    analyzer = _analyzer_type()(
        DetectionContext([], []),
        density="sparse_live",
        buffer=_buffer_type()(clock=_Clock(BASE + timedelta(minutes=10))),
    )

    result = analyzer.update([_obs(0)])

    assert result.events == []
    assert result.alerts == []
