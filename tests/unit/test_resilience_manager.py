from __future__ import annotations

from apps.api.seawatch.live.config import LiveRuntimeConfig
from apps.api.seawatch.live.resilience import (
    CoverageKind,
    EdgeInputKind,
    OperatingMode,
    ResilienceModeManager,
    SourceHealthSnapshot,
)


class Clock:
    def __init__(self, value: float = 100.0) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value


def _source(
    name: str,
    last: float | None,
    *,
    kind: EdgeInputKind | None = None,
    count: int = 1,
) -> SourceHealthSnapshot:
    return SourceHealthSnapshot(
        source=name,
        connected=last is not None,
        last_message_at=None,
        last_message_monotonic=last,
        vessel_count=count if last is not None else 0,
        input_kind=kind,
    )


def _manager(clock: Clock) -> ResilienceModeManager:
    return ResilienceModeManager(LiveRuntimeConfig.from_env({}), monotonic=clock)


def test_mode_precedence_cloud_edge_replay_none_and_explicit_demo() -> None:
    clock = Clock()

    cloud = _manager(clock).evaluate(
        _source("cloud", 99.0), _source("edge", 99.0, kind=EdgeInputKind.UDP)
    )
    edge = _manager(clock).evaluate(
        _source("cloud", 60.0), _source("edge", 99.0, kind=EdgeInputKind.UDP)
    )
    replay = _manager(clock).evaluate(
        _source("cloud", None), _source("edge", 99.0, kind=EdgeInputKind.REPLAY)
    )
    none = _manager(clock).evaluate(
        _source("cloud", None), _source("edge", None, kind=EdgeInputKind.DISABLED)
    )
    demo = _manager(clock).evaluate(
        _source("cloud", 99.0),
        _source("edge", 99.0, kind=EdgeInputKind.UDP),
        offline_demo=True,
    )

    assert (cloud.mode, cloud.coverage, cloud.simulated) == (
        OperatingMode.CLOUD_LIVE,
        CoverageKind.CLOUD,
        False,
    )
    assert edge.mode is OperatingMode.EDGE_LIVE
    assert replay.mode is OperatingMode.EDGE_REPLAY
    assert replay.simulated is True
    assert none.mode is OperatingMode.NO_LIVE_SOURCE
    assert demo.mode is OperatingMode.OFFLINE_DEMO
    assert demo.simulated is True


def test_exact_stale_boundary_is_fresh_then_expires() -> None:
    clock = Clock(100.0)
    manager = _manager(clock)

    at_boundary = manager.evaluate(
        _source("cloud", 70.0), _source("edge", None, kind=EdgeInputKind.DISABLED)
    )
    clock.value = 100.001
    after_boundary = manager.evaluate(
        _source("cloud", 70.0), _source("edge", None, kind=EdgeInputKind.DISABLED)
    )

    assert at_boundary.cloud.fresh is True
    assert at_boundary.cloud.message_age_seconds == 30.0
    assert after_boundary.cloud.fresh is False
    assert after_boundary.mode is OperatingMode.NO_LIVE_SOURCE


def test_cloud_recovery_requires_twenty_continuous_seconds() -> None:
    clock = Clock(100.0)
    manager = _manager(clock)
    edge = _source("edge", 100.0, kind=EdgeInputKind.UDP)

    assert manager.evaluate(_source("cloud", 60.0), edge).mode is OperatingMode.EDGE_LIVE
    clock.value = 101.0
    assert manager.evaluate(_source("cloud", 101.0), edge).mode is OperatingMode.EDGE_LIVE
    clock.value = 120.999
    edge = _source("edge", 120.0, kind=EdgeInputKind.UDP)
    assert manager.evaluate(_source("cloud", 120.0), edge).mode is OperatingMode.EDGE_LIVE
    clock.value = 121.0
    assert manager.evaluate(_source("cloud", 121.0), edge).mode is OperatingMode.CLOUD_LIVE


def test_interrupted_cloud_recovery_restarts_the_interval() -> None:
    clock = Clock(100.0)
    manager = _manager(clock)
    edge = _source("edge", 100.0, kind=EdgeInputKind.UDP)
    manager.evaluate(_source("cloud", None), edge)

    clock.value = 101.0
    manager.evaluate(_source("cloud", 101.0), edge)
    clock.value = 110.0
    manager.evaluate(_source("cloud", 70.0), edge)
    clock.value = 111.0
    manager.evaluate(_source("cloud", 111.0), edge)
    clock.value = 130.9
    edge = _source("edge", 130.0, kind=EdgeInputKind.UDP)
    assert manager.evaluate(_source("cloud", 130.0), edge).mode is OperatingMode.EDGE_LIVE
    clock.value = 131.0
    assert manager.evaluate(_source("cloud", 131.0), edge).mode is OperatingMode.CLOUD_LIVE


def test_edge_staling_during_recovery_returns_to_fresh_cloud() -> None:
    clock = Clock(100.0)
    manager = _manager(clock)
    manager.evaluate(
        _source("cloud", None), _source("edge", 100.0, kind=EdgeInputKind.UDP)
    )
    clock.value = 105.0
    manager.evaluate(
        _source("cloud", 105.0), _source("edge", 100.0, kind=EdgeInputKind.UDP)
    )
    clock.value = 131.0
    status = manager.evaluate(
        _source("cloud", 131.0), _source("edge", 100.0, kind=EdgeInputKind.UDP)
    )

    assert status.edge.fresh is False
    assert status.mode is OperatingMode.CLOUD_LIVE


def test_decreasing_and_frozen_clock_never_makes_negative_age_or_early_recovery() -> None:
    clock = Clock(100.0)
    manager = _manager(clock)
    edge = _source("edge", 100.0, kind=EdgeInputKind.REPLAY)
    manager.evaluate(_source("cloud", None), edge)

    clock.value = 101.0
    manager.evaluate(_source("cloud", 101.0), edge)
    clock.value = 90.0
    backwards = manager.evaluate(_source("cloud", 101.0), edge)
    frozen = manager.evaluate(_source("cloud", 101.0), edge)

    assert backwards.cloud.message_age_seconds == 0.0
    assert backwards.mode is OperatingMode.EDGE_REPLAY
    assert frozen.mode is OperatingMode.EDGE_REPLAY

    clock.value = 121.0
    assert manager.evaluate(_source("cloud", 121.0), edge).mode is OperatingMode.CLOUD_LIVE


def test_large_forward_jump_expires_sources_without_wall_timestamps() -> None:
    clock = Clock(100.0)
    manager = _manager(clock)
    cloud = _source("cloud", 100.0)
    edge = _source("edge", 100.0, kind=EdgeInputKind.UDP)
    manager.evaluate(cloud, edge)

    clock.value = 10_000.0
    status = manager.evaluate(cloud, edge)

    assert status.mode is OperatingMode.NO_LIVE_SOURCE
    assert status.cloud.fresh is False
    assert status.edge.fresh is False
    assert status.cloud.message_age_seconds == 9_900.0
    assert manager.current_mode is OperatingMode.NO_LIVE_SOURCE
