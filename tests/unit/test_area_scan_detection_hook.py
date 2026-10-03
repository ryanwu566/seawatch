from __future__ import annotations

import asyncio
import logging
import json
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from apps.api.seawatch.detection.context import DetectionContext
from apps.api.seawatch.detection.engine import AnalysisResult
from apps.api.seawatch.detection.live_adapter import (
    LiveDetectionAnalyzer,
    RollingTrackBuffer,
)
from apps.api.seawatch.live.identity import VesselIdentityRegistry
from apps.api.seawatch.live.schema import LiveVesselObservation


BASE = datetime(2026, 10, 4, 1, 0, tzinfo=timezone.utc)
TEST_SIGNING_KEY = "signing-secret-at-least-32-bytes"
TEST_OPERATOR_KEY = "operator-secret-at-least-32-bytes"


class _Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


def _observation(
    seconds: int = 0,
    *,
    mmsi: int = 416_000_001,
    provider_id: str = "provider-a",
    latitude: float = 23.5,
    longitude: float = 121.0,
    received_seconds: int | None = None,
) -> LiveVesselObservation:
    observed_at = BASE + timedelta(seconds=seconds)
    return LiveVesselObservation(
        provider_id=provider_id,
        latitude=latitude,
        longitude=longitude,
        observed_at=observed_at,
        received_at=BASE
        + timedelta(seconds=seconds if received_seconds is None else received_seconds),
        source="datalastic",
        sog_knots=8.0,
        cog_deg=90.0,
        name="SEA TEST",
        mmsi=mmsi,
    )


def _scan_request():
    from apps.api.seawatch.live.area_scan import AreaScanRequest

    return AreaScanRequest.model_validate(
        {
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [120.0, 22.0],
                        [121.0, 22.0],
                        [121.0, 23.0],
                        [120.0, 23.0],
                        [120.0, 22.0],
                    ]
                ],
            }
        }
    )


def _provider_vessel(
    *,
    mmsi: int = 416_000_001,
    observed_at: datetime | None = BASE,
    longitude: float = 120.5,
):
    from apps.api.seawatch.live.datalastic import DatalasticVessel

    return DatalasticVessel(
        uuid=f"provider-{mmsi}",
        name="REAL SHIP",
        mmsi=mmsi,
        imo=9_876_543,
        latitude=22.5,
        longitude=longitude,
        speed_knots=8.0,
        course_deg=180.0,
        heading_deg=179.0,
        navigation_status="Under way using engine",
        vessel_type="Cargo",
        vessel_type_specific="Container Ship",
        destination="KHH",
        observed_at=observed_at,
    )


class _AreaProvider:
    def __init__(self, results=(), error: Exception | None = None) -> None:
        self.results = tuple(results)
        self.error = error
        self.calls = 0

    async def scan(self, _queries):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.results


def _live_alert_fixture():
    import numpy as np

    from apps.api.seawatch.detection.alerts import build_alerts
    from apps.api.seawatch.detection.config import DetectionConfig
    from apps.api.seawatch.detection.models import Event, Track

    raw_mmsi = "416000001"
    track = Track(
        mmsi=raw_mmsi,
        name=raw_mmsi,
        ship_type="cargo",
        flag="",
        t=np.asarray([BASE.timestamp(), (BASE + timedelta(minutes=10)).timestamp()]),
        lat=np.asarray([22.5, 22.6]),
        lon=np.asarray([120.5, 120.6]),
        sog=np.asarray([8.0, 8.0]),
        cog=np.asarray([90.0, 90.0]),
    )
    event = Event(
        id="E-live",
        kind="position_jump",
        mmsis=[raw_mmsi],
        t_start=track.t[0],
        t_end=track.t[-1],
        lat=22.55,
        lon=120.55,
        severity=90.0,
        confidence=0.8,
        summary=f"{raw_mmsi}: behavioral position anomaly",
        evidence=[f"Vessel {raw_mmsi} reported an implausible jump."],
        benign_explanations=["Receiver or GNSS error"],
        uncertainty=["AIS cannot establish intent."],
        metrics={"raw_reference": raw_mmsi},
        path=[(22.5, 120.5), (22.6, 120.6)],
    )
    alerts = build_alerts(
        [event],
        [track],
        DetectionConfig(alert_min_risk=0),
    )
    assert len(alerts) == 1
    return track, event, alerts[0]


def _runtime_with_real_analyzer(*, max_vessels: int = 1_000):
    from apps.api.seawatch.detection.live_runtime import (
        LiveDetectionComponents,
        LiveDetectionRuntime,
    )

    context = DetectionContext([], [])
    clock = _Clock(BASE + timedelta(minutes=10))
    analyzer = LiveDetectionAnalyzer(
        context,
        density="sparse_live",
        buffer=RollingTrackBuffer(
            max_vessels=max_vessels,
            stale_after=timedelta(minutes=15),
            clock=clock,
        ),
    )
    registry = VesselIdentityRegistry("stable-live-detection-test-key")
    components = LiveDetectionComponents(
        analyzer=analyzer,
        context=context,
        context_quality="historical",
    )
    runtime = LiveDetectionRuntime(
        registry,
        component_factory=lambda: components,
        clock=clock,
    )
    return runtime, analyzer, context, clock


def test_runtime_starts_without_claiming_an_analysis_is_ready() -> None:
    runtime, _analyzer, _context, _clock = _runtime_with_real_analyzer()

    snapshot = runtime.snapshot()

    assert snapshot.status == "insufficient_history"
    assert snapshot.scanned_at is None
    assert snapshot.analysis_at is None


def test_first_scan_is_cached_as_honest_insufficient_history() -> None:
    runtime, _analyzer, _context, _clock = _runtime_with_real_analyzer()

    snapshot = runtime.update([_observation()], scanned_at=BASE + timedelta(minutes=10))

    assert snapshot.status == "insufficient_history"
    assert snapshot.n_tracks == 1
    assert snapshot.n_analyzed == 0
    assert snapshot.alert_count == 0
    assert snapshot.analysis_at == BASE + timedelta(minutes=10)
    assert runtime.latest_result is not None
    assert runtime.latest_result.alerts == []


def test_repeated_scans_accumulate_new_fixes_but_not_receipt_only_repolls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from apps.api.seawatch.detection import live_adapter

    runtime, analyzer, context, clock = _runtime_with_real_analyzer()
    calls: list[tuple[list[Any], DetectionContext]] = []

    def capture_fleet(
        tracks: list[Any], supplied_context: DetectionContext, **kwargs: Any
    ) -> AnalysisResult:
        calls.append((tracks, supplied_context))
        return AnalysisResult(
            [],
            [],
            n_tracks=len(tracks),
            n_analyzed=len(tracks),
            density=kwargs["density"],
        )

    monkeypatch.setattr(live_adapter.engine, "analyze", capture_fleet)

    runtime.update([_observation(0)], scanned_at=clock.now)
    runtime.update(
        [_observation(0, received_seconds=120)],
        scanned_at=clock.now + timedelta(minutes=2),
    )
    runtime.update(
        [_observation(180, latitude=23.51, longitude=121.01)],
        scanned_at=clock.now + timedelta(minutes=3),
    )

    tracks = analyzer.tracks()
    assert len(calls) == 3
    assert all(supplied is context for _, supplied in calls)
    assert all(len(fleet) == 1 for fleet, _ in calls)
    assert len(tracks) == 1
    assert tracks[0].t.tolist() == [
        BASE.timestamp(),
        (BASE + timedelta(seconds=180)).timestamp(),
    ]


def test_runtime_passes_the_entire_fleet_to_one_engine_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from apps.api.seawatch.detection import live_adapter

    runtime, _analyzer, context, clock = _runtime_with_real_analyzer()
    calls: list[tuple[list[Any], DetectionContext]] = []

    def capture_fleet(
        tracks: list[Any], supplied_context: DetectionContext, **kwargs: Any
    ) -> AnalysisResult:
        calls.append((tracks, supplied_context))
        return AnalysisResult([], [], n_tracks=len(tracks), n_analyzed=len(tracks))

    monkeypatch.setattr(live_adapter.engine, "analyze", capture_fleet)

    runtime.update(
        [
            _observation(mmsi=416_000_001, provider_id="one"),
            _observation(mmsi=416_000_002, provider_id="two"),
        ],
        scanned_at=clock.now,
    )

    assert len(calls) == 1
    assert len(calls[0][0]) == 2
    assert calls[0][1] is context


@dataclass
class _StubAnalyzer:
    results: list[AnalysisResult | Exception]
    tracks_value: list[Any]

    def __post_init__(self) -> None:
        self.calls = 0

    def update(self, observations, *, as_of=None) -> AnalysisResult:
        del observations, as_of
        item = self.results[min(self.calls, len(self.results) - 1)]
        self.calls += 1
        if isinstance(item, Exception):
            raise item
        return item

    def tracks(self) -> list[Any]:
        return self.tracks_value


def test_failed_analysis_preserves_the_latest_successful_result() -> None:
    from apps.api.seawatch.detection.live_runtime import (
        LiveDetectionComponents,
        LiveDetectionRuntime,
    )

    success = AnalysisResult([], [], n_tracks=1, n_analyzed=1)
    analyzer = _StubAnalyzer([success, RuntimeError("detector exploded")], [])
    runtime = LiveDetectionRuntime(
        VesselIdentityRegistry("stable-live-detection-test-key"),
        component_factory=lambda: LiveDetectionComponents(
            analyzer=analyzer,
            context=DetectionContext([], []),
            context_quality="historical",
        ),
        clock=_Clock(BASE),
    )

    first = runtime.update([_observation()], scanned_at=BASE)
    failed = runtime.update([_observation(60)], scanned_at=BASE + timedelta(minutes=1))

    assert first.status == "ready"
    assert failed.status == "error"
    assert failed.error_code == "analysis_error"
    assert failed.analysis_at == BASE
    assert failed.scanned_at == BASE + timedelta(minutes=1)
    assert runtime.latest_result is success


def test_component_factory_failure_is_context_unavailable_and_non_raising() -> None:
    from apps.api.seawatch.detection.live_runtime import LiveDetectionRuntime

    def unavailable():
        raise RuntimeError("historical bundle missing")

    runtime = LiveDetectionRuntime(
        VesselIdentityRegistry("stable-live-detection-test-key"),
        component_factory=unavailable,
        clock=_Clock(BASE),
    )

    snapshot = runtime.update([_observation()], scanned_at=BASE)

    assert snapshot.status == "context_unavailable"
    assert snapshot.error_code == "context_unavailable"
    assert snapshot.analysis_at is None
    assert runtime.latest_result is None


def test_optional_ml_runs_only_for_existing_alert_candidates() -> None:
    from apps.api.seawatch.detection.live_runtime import (
        LiveDetectionComponents,
        LiveDetectionRuntime,
    )

    alert = SimpleNamespace(
        ml=None,
        id="A-live",
        events=[],
        t_end=BASE.timestamp(),
        raised_at=0.0,
    )
    analyzer = _StubAnalyzer(
        [AnalysisResult([], [alert], n_tracks=1, n_analyzed=1)],
        [SimpleNamespace(mmsi="416000001")],
    )
    ml_calls: list[tuple[list[Any], list[Any]]] = []

    def score(tracks: list[Any], alerts: list[Any]) -> None:
        ml_calls.append((tracks, alerts))
        alerts[0].ml = {"available": True, "agreement": "agree"}

    runtime = LiveDetectionRuntime(
        VesselIdentityRegistry("stable-live-detection-test-key"),
        component_factory=lambda: LiveDetectionComponents(
            analyzer=analyzer,
            context=DetectionContext([], []),
            context_quality="historical",
            ml_scorer=score,
            ml_available=True,
        ),
        clock=_Clock(BASE),
    )

    snapshot = runtime.update([_observation()], scanned_at=BASE)

    assert snapshot.status == "ready"
    assert len(ml_calls) == 1
    assert alert.ml == {"available": True, "agreement": "agree"}


def test_missing_ml_scorer_leaves_alert_ml_none_without_breaking_detection() -> None:
    from apps.api.seawatch.detection.live_runtime import (
        LiveDetectionComponents,
        LiveDetectionRuntime,
    )

    alert = SimpleNamespace(
        ml=None,
        id="A-live",
        events=[],
        t_end=BASE.timestamp(),
        raised_at=0.0,
    )
    analyzer = _StubAnalyzer(
        [AnalysisResult([], [alert], n_tracks=1, n_analyzed=1)],
        [],
    )
    runtime = LiveDetectionRuntime(
        VesselIdentityRegistry("stable-live-detection-test-key"),
        component_factory=lambda: LiveDetectionComponents(
            analyzer=analyzer,
            context=DetectionContext([], []),
            context_quality="historical",
        ),
        clock=_Clock(BASE),
    )

    snapshot = runtime.update([_observation()], scanned_at=BASE)

    assert snapshot.status == "ready"
    assert snapshot.ml_available is False
    assert alert.ml is None


def test_ml_failure_degrades_but_keeps_deterministic_result() -> None:
    from apps.api.seawatch.detection.live_runtime import (
        LiveDetectionComponents,
        LiveDetectionRuntime,
    )

    alert = SimpleNamespace(
        ml=None,
        id="A-live",
        events=[],
        t_end=BASE.timestamp(),
        raised_at=0.0,
    )
    result = AnalysisResult([], [alert], n_tracks=1, n_analyzed=1)
    analyzer = _StubAnalyzer([result], [])

    def fail_ml(_tracks: list[Any], _alerts: list[Any]) -> None:
        raise ValueError("model incompatible")

    runtime = LiveDetectionRuntime(
        VesselIdentityRegistry("stable-live-detection-test-key"),
        component_factory=lambda: LiveDetectionComponents(
            analyzer=analyzer,
            context=DetectionContext([], []),
            context_quality="historical",
            ml_scorer=fail_ml,
            ml_available=True,
        ),
        clock=_Clock(BASE),
    )

    snapshot = runtime.update([_observation()], scanned_at=BASE)

    assert snapshot.status == "degraded"
    assert snapshot.error_code == "ml_unavailable"
    assert runtime.latest_result is result
    assert alert.ml is None


def test_runtime_serializes_concurrent_updates() -> None:
    from apps.api.seawatch.detection.live_runtime import (
        LiveDetectionComponents,
        LiveDetectionRuntime,
    )

    state_lock = threading.Lock()
    active = 0
    max_active = 0

    class SlowAnalyzer:
        def update(self, observations, *, as_of=None) -> AnalysisResult:
            nonlocal active, max_active
            del observations, as_of
            with state_lock:
                active += 1
                max_active = max(max_active, active)
            time.sleep(0.02)
            with state_lock:
                active -= 1
            return AnalysisResult([], [], n_tracks=1, n_analyzed=1)

        def tracks(self) -> list[Any]:
            return []

    analyzer = SlowAnalyzer()
    runtime = LiveDetectionRuntime(
        VesselIdentityRegistry("stable-live-detection-test-key"),
        component_factory=lambda: LiveDetectionComponents(
            analyzer=analyzer,
            context=DetectionContext([], []),
            context_quality="historical",
        ),
        clock=_Clock(BASE),
    )
    errors: list[BaseException] = []

    def update(seconds: int) -> None:
        try:
            runtime.update(
                [_observation(seconds)],
                scanned_at=BASE + timedelta(seconds=seconds),
            )
        except BaseException as exc:  # pragma: no cover - assertion captures it
            errors.append(exc)

    threads = [threading.Thread(target=update, args=(seconds,)) for seconds in (0, 60)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert max_active == 1


def test_runtime_remains_bounded_by_the_canonical_buffer_limits() -> None:
    runtime, analyzer, _context, clock = _runtime_with_real_analyzer(max_vessels=2)

    runtime.update(
        [
            _observation(mmsi=416_000_001, provider_id="one"),
            _observation(mmsi=416_000_002, provider_id="two"),
            _observation(mmsi=416_000_003, provider_id="three"),
        ],
        scanned_at=clock.now,
    )

    assert len(analyzer.tracks()) == 2


def test_default_components_reuse_real_learned_context_without_sharing_stats(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from apps.api.seawatch.detection import service as service_module
    from apps.api.seawatch.detection.live_runtime import (
        build_live_detection_components,
    )
    from apps.api.seawatch.detection.context import TrafficBaseline
    from apps.api.seawatch.detection.state import FeedbackStore

    source_context = DetectionContext([], [], TrafficBaseline(counts={(1, 1): 3}))
    source_context.learned = object()
    source_context.habits = object()
    source_context.territory = object()
    service = SimpleNamespace(
        info={"data_kind": "real"},
        region="taiwan-day",
        store=FeedbackStore(None),
        watch=None,
        ml_models=None,
        _context=lambda: source_context,
    )
    monkeypatch.setattr(service_module, "get_service", lambda: service)

    components = build_live_detection_components()

    assert components.context is not source_context
    assert components.context.baseline is source_context.baseline
    assert components.context.learned is source_context.learned
    assert components.context.habits is source_context.habits
    assert components.context.territory is source_context.territory
    assert components.context_quality == "historical"
    assert components.context_source == "taiwan-day"


def test_default_components_never_use_simulated_baseline_for_live_observations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from apps.api.seawatch.detection import service as service_module
    from apps.api.seawatch.detection.context import TrafficBaseline
    from apps.api.seawatch.detection.live_runtime import (
        build_live_detection_components,
    )
    from apps.api.seawatch.detection.state import FeedbackStore

    simulated_context = DetectionContext(
        [], [], TrafficBaseline(counts={(1, 1): 999}, n_vessels=999)
    )
    service = SimpleNamespace(
        info={"data_kind": "simulated"},
        region="taiwan",
        store=FeedbackStore(None),
        watch=None,
        ml_models=None,
        _context=lambda: simulated_context,
    )
    monkeypatch.setattr(service_module, "get_service", lambda: service)

    components = build_live_detection_components()

    assert components.context is not simulated_context
    assert components.context.baseline is None
    assert components.context.learned is None
    assert components.context.territory is not None
    assert components.context_quality == "static_only"


def test_live_runtime_owns_one_process_wide_detection_runtime() -> None:
    from apps.api.seawatch.live.runtime import get_live_runtime, reset_live_runtime

    reset_live_runtime()
    try:
        first = get_live_runtime()
        second = get_live_runtime()

        assert first is second
        assert first.live_detection is second.live_detection
    finally:
        reset_live_runtime()


def test_area_scan_delivers_one_normalized_batch_once_without_extra_provider_calls() -> None:
    from apps.api.seawatch.live.area_scan import AreaScanService

    provider = _AreaProvider((_provider_vessel(),))
    delivered: list[tuple[tuple[LiveVesselObservation, ...], datetime]] = []

    async def sink(
        observations: tuple[LiveVesselObservation, ...], scanned_at: datetime
    ) -> None:
        delivered.append((observations, scanned_at))

    service = AreaScanService(
        provider=provider,
        identity_registry=VesselIdentityRegistry("stable-test-key"),
        observation_sink=sink,
        clock=lambda: BASE + timedelta(minutes=10),
    )

    first = asyncio.run(service.scan(_scan_request()))
    cached = asyncio.run(service.scan(_scan_request()))

    assert first.cached is False
    assert cached.cached is True
    assert provider.calls == 1
    assert len(delivered) == 1
    assert len(delivered[0][0]) == 1
    assert delivered[0][0][0].mmsi == 416_000_001
    assert delivered[0][1] == BASE + timedelta(minutes=10)


def test_coalesced_area_scan_waiters_share_one_detection_delivery() -> None:
    from apps.api.seawatch.live.area_scan import AreaScanService

    release = asyncio.Event()
    entered = asyncio.Event()

    class BlockingProvider(_AreaProvider):
        async def scan(self, queries):
            self.calls += 1
            entered.set()
            await release.wait()
            return self.results

    provider = BlockingProvider((_provider_vessel(),))
    delivered: list[tuple[LiveVesselObservation, ...]] = []

    async def sink(observations, _scanned_at) -> None:
        delivered.append(tuple(observations))

    service = AreaScanService(
        provider=provider,
        identity_registry=VesselIdentityRegistry("stable-test-key"),
        observation_sink=sink,
        clock=lambda: BASE + timedelta(minutes=10),
    )

    async def run():
        owner = asyncio.create_task(service.scan(_scan_request()))
        await entered.wait()
        waiter = asyncio.create_task(service.scan(_scan_request()))
        release.set()
        return await asyncio.gather(owner, waiter)

    owner, waiter = asyncio.run(run())

    assert provider.calls == 1
    assert len(delivered) == 1
    assert owner.cached is False
    assert waiter.cached is True


def test_provider_failure_never_delivers_a_detection_batch() -> None:
    from apps.api.seawatch.live.area_scan import AreaScanService
    from apps.api.seawatch.live.datalastic import (
        ProviderError,
        ProviderErrorCategory,
    )

    provider = _AreaProvider(error=ProviderError(ProviderErrorCategory.TIMEOUT))
    delivered: list[Any] = []
    service = AreaScanService(
        provider=provider,
        identity_registry=VesselIdentityRegistry("stable-test-key"),
        observation_sink=lambda *args: delivered.append(args),
    )

    with pytest.raises(ProviderError):
        asyncio.run(service.scan(_scan_request()))

    assert provider.calls == 1
    assert delivered == []


def test_detection_failure_does_not_break_a_successful_paid_scan(
    caplog: pytest.LogCaptureFixture,
) -> None:
    from apps.api.seawatch.live.area_scan import AreaScanService

    provider = _AreaProvider((_provider_vessel(),))

    async def fail_detection(_observations, _scanned_at) -> None:
        raise RuntimeError("private-detector-error-detail")

    service = AreaScanService(
        provider=provider,
        identity_registry=VesselIdentityRegistry("stable-test-key"),
        observation_sink=fail_detection,
        clock=lambda: BASE + timedelta(minutes=10),
    )

    with caplog.at_level(logging.WARNING, logger="seawatch.live.area_scan"):
        result = asyncio.run(service.scan(_scan_request()))

    assert result.total == 1
    assert provider.calls == 1
    assert "Live Detection update failed" in caplog.text
    assert "private-detector-error-detail" not in caplog.text


def test_unknown_provider_time_is_displayed_but_not_treated_as_detection_motion() -> None:
    from apps.api.seawatch.live.area_scan import AreaScanService

    provider = _AreaProvider(
        (
            _provider_vessel(mmsi=416_000_001, observed_at=BASE),
            _provider_vessel(mmsi=416_000_002, observed_at=None, longitude=120.6),
        )
    )
    delivered: list[tuple[LiveVesselObservation, ...]] = []

    async def sink(observations, _scanned_at) -> None:
        delivered.append(tuple(observations))

    service = AreaScanService(
        provider=provider,
        identity_registry=VesselIdentityRegistry("stable-test-key"),
        observation_sink=sink,
        clock=lambda: BASE + timedelta(minutes=10),
    )

    result = asyncio.run(service.scan(_scan_request()))
    public = result.to_public_dict()

    assert result.total == 2
    assert len(delivered) == 1
    assert [item.mmsi for item in delivered[0]] == [416_000_001]
    unknown = next(
        feature
        for feature in public["vessels"]
        if feature["properties"]["freshness_state"] == "unknown"
    )
    assert unknown["properties"]["observed_at"] is None


def test_observed_scanned_and_analysis_times_remain_distinct() -> None:
    from apps.api.seawatch.detection.live_runtime import (
        LiveDetectionComponents,
        LiveDetectionRuntime,
    )
    from apps.api.seawatch.live.area_scan import AreaScanService

    scanned_at = BASE + timedelta(minutes=10)
    analysis_at = BASE + timedelta(minutes=11)
    analyzer = _StubAnalyzer(
        [AnalysisResult([], [], n_tracks=1, n_analyzed=1)],
        [],
    )
    runtime = LiveDetectionRuntime(
        VesselIdentityRegistry("stable-test-key"),
        component_factory=lambda: LiveDetectionComponents(
            analyzer=analyzer,
            context=DetectionContext([], []),
            context_quality="historical",
        ),
        clock=_Clock(analysis_at),
    )
    delivered_observed_at: list[datetime] = []

    def sink(observations, scanned_at: datetime) -> None:
        delivered_observed_at.extend(item.observed_at for item in observations)
        runtime.update(observations, scanned_at=scanned_at)

    service = AreaScanService(
        provider=_AreaProvider((_provider_vessel(observed_at=BASE),)),
        identity_registry=VesselIdentityRegistry("stable-test-key"),
        observation_sink=sink,
        clock=lambda: scanned_at,
    )

    result = asyncio.run(service.scan(_scan_request()))
    snapshot = runtime.snapshot()

    assert delivered_observed_at == [BASE]
    assert result.scanned_at == scanned_at
    assert snapshot.analysis_at == analysis_at
    assert len({delivered_observed_at[0], result.scanned_at, snapshot.analysis_at}) == 3


def test_area_scan_api_exposes_detection_state_separately(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from apps.api.seawatch.detection.live_runtime import LiveDetectionSnapshot
    from apps.api.seawatch.live.area_scan_access import mint_area_scan_capability
    from apps.api.seawatch.live.datalastic import DatalasticClient, DatalasticStatus
    from apps.api.seawatch.live.runtime import get_live_runtime, reset_live_runtime
    from apps.api.seawatch.main import create_app

    monkeypatch.setenv("DATALASTIC_API_KEY", "route-secret")
    monkeypatch.setenv("SEAWATCH_IDENTITY_KEY", "stable-test-key")
    monkeypatch.setenv("SEAWATCH_AREA_SCAN_SIGNING_KEY", TEST_SIGNING_KEY)
    monkeypatch.setenv("SEAWATCH_AREA_SCAN_OPERATOR_KEY", TEST_OPERATOR_KEY)

    async def healthy_stat(_client):
        return DatalasticStatus(
            configured=True,
            reachable=True,
            key_status="valid",
            addons=False,
            requests_remaining=10,
            rate_limit_remaining=10,
            last_success_at=BASE,
            last_error_category=None,
        )

    monkeypatch.setattr(DatalasticClient, "stat", healthy_stat)
    reset_live_runtime()
    runtime = get_live_runtime()
    provider = _AreaProvider((_provider_vessel(),))
    runtime.area_scan_service.set_provider(provider)
    snapshot = LiveDetectionSnapshot(
        status="insufficient_history",
        scanned_at=BASE + timedelta(minutes=10),
        analysis_at=BASE + timedelta(minutes=11),
        n_tracks=1,
    )

    def update(_observations, *, scanned_at):
        del scanned_at
        runtime.live_detection._snapshot = snapshot
        return snapshot

    monkeypatch.setattr(runtime.live_detection, "update", update)
    headers = {
        "Authorization": "Bearer "
        + mint_area_scan_capability(runtime.area_scan_access)
    }

    try:
        with TestClient(create_app()) as client:
            response = client.post(
                "/live/area-scan",
                json=_scan_request().model_dump(),
                headers=headers,
            )
        body = response.json()
        assert response.status_code == 200
        assert body["total"] == 1
        assert body["detection"]["status"] == "insufficient_history"
        assert body["detection"]["scanned_at"] == "2026-10-04T01:10:00+00:00"
        assert body["detection"]["analysis_at"] == "2026-10-04T01:11:00+00:00"
        assert provider.calls == 1
    finally:
        reset_live_runtime()


def test_live_detection_public_payloads_link_alert_and_track_with_opaque_id() -> None:
    from apps.api.seawatch.detection.live_runtime import (
        LiveDetectionComponents,
        LiveDetectionRuntime,
    )
    from apps.api.seawatch.detection.state import FeedbackStore

    track, event, alert = _live_alert_fixture()
    analyzer = _StubAnalyzer(
        [AnalysisResult([event], [alert], n_tracks=1, n_analyzed=1)],
        [track],
    )
    registry = VesselIdentityRegistry("stable-test-key")
    feedback = FeedbackStore(None)
    runtime = LiveDetectionRuntime(
        registry,
        component_factory=lambda: LiveDetectionComponents(
            analyzer=analyzer,
            context=DetectionContext([], []),
            context_quality="historical",
            feedback=feedback,
        ),
        clock=_Clock(BASE + timedelta(minutes=11)),
    )
    runtime.update([_observation()], scanned_at=BASE + timedelta(minutes=10))

    public_id = registry.public_id_for_mmsi(416_000_001)
    tracks = runtime.public_tracks()
    alerts = runtime.public_alerts()
    detail = runtime.public_alert(alert.id)

    assert public_id is not None
    assert tracks[0]["mmsi"] == tracks[0]["public_id"] == public_id
    assert alerts[0]["mmsis"] == [public_id]
    assert alerts[0]["public_ids"] == [public_id]
    assert alerts[0]["vessels"][0]["public_id"] == public_id
    assert alerts[0]["raised_at"] == event.t_end
    assert detail is not None
    assert detail["timeline"][0]["mmsis"] == [public_id]
    serialized = json.dumps(
        {"tracks": tracks, "alerts": alerts, "detail": detail},
        sort_keys=True,
    )
    assert "416000001" not in serialized
    assert "provider-a" not in serialized


def test_live_detection_public_meta_carries_status_and_analysis_timestamp() -> None:
    from apps.api.seawatch.detection.live_runtime import (
        LiveDetectionComponents,
        LiveDetectionRuntime,
    )

    track, event, alert = _live_alert_fixture()
    analyzer = _StubAnalyzer(
        [AnalysisResult([event], [alert], n_tracks=1, n_analyzed=1)],
        [track],
    )
    runtime = LiveDetectionRuntime(
        VesselIdentityRegistry("stable-test-key"),
        component_factory=lambda: LiveDetectionComponents(
            analyzer=analyzer,
            context=DetectionContext([], []),
            context_quality="historical",
            context_source="taiwan-day",
        ),
        clock=_Clock(BASE + timedelta(minutes=11)),
    )
    runtime.update([_observation()], scanned_at=BASE + timedelta(minutes=10))

    meta = runtime.public_meta()

    assert meta["region"] == "live"
    assert meta["data_kind"] == "real"
    assert meta["simulated"] is False
    assert meta["vessels"] == 1
    assert meta["fixes"] == 2
    assert meta["t0"] == BASE.timestamp()
    assert meta["t1"] == (BASE + timedelta(minutes=10)).timestamp()
    assert meta["source"] == "live"
    assert meta["detection_status"] == "ready"
    assert meta["analysis_at"] == "2026-10-04T01:11:00+00:00"


def test_live_detection_api_reuses_watch_floor_shapes_without_scenario_or_path_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from apps.api.seawatch.api import detection as detection_api
    from apps.api.seawatch.detection.live_runtime import (
        LiveDetectionComponents,
        LiveDetectionRuntime,
    )
    from apps.api.seawatch.detection.state import FeedbackStore
    from apps.api.seawatch.main import create_app

    track, event, alert = _live_alert_fixture()
    feedback = FeedbackStore(None)
    analyzer = _StubAnalyzer(
        [AnalysisResult([event], [alert], n_tracks=1, n_analyzed=1)],
        [track],
    )
    runtime = LiveDetectionRuntime(
        VesselIdentityRegistry("stable-test-key"),
        component_factory=lambda: LiveDetectionComponents(
            analyzer=analyzer,
            context=DetectionContext([], []),
            context_quality="historical",
            feedback=feedback,
        ),
        clock=_Clock(BASE + timedelta(minutes=11)),
    )
    runtime.update([_observation()], scanned_at=BASE + timedelta(minutes=10))
    monkeypatch.setattr(
        detection_api,
        "get_live_runtime",
        lambda: SimpleNamespace(live_detection=runtime),
        raising=False,
    )

    def scenario_must_not_load():
        raise AssertionError("live API touched scenario/path-agent state")

    monkeypatch.setattr(detection_api, "get_service", scenario_must_not_load)
    client = TestClient(create_app())

    scenario_response = client.get("/detection/scenario?source=live")
    tracks_response = client.get("/detection/tracks?source=live")
    alerts_response = client.get("/detection/alerts?source=live")
    detail_response = client.get(f"/detection/alerts/{alert.id}?source=live")

    assert scenario_response.status_code == 200
    assert tracks_response.status_code == 200
    assert alerts_response.status_code == 200
    assert detail_response.status_code == 200
    assert scenario_response.json()["detection_status"] == "ready"
    assert tracks_response.json()["source"] == "live"
    assert alerts_response.json()["source"] == "live"
    assert detail_response.json()["source"] == "live"
    assert detail_response.json()["path_reviews"] == []
    assert "416000001" not in (
        scenario_response.text
        + tracks_response.text
        + alerts_response.text
        + detail_response.text
    )


def test_live_alert_feedback_mutations_are_source_scoped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from apps.api.seawatch.api import detection as detection_api
    from apps.api.seawatch.detection.live_runtime import (
        LiveDetectionComponents,
        LiveDetectionRuntime,
    )
    from apps.api.seawatch.detection.state import FeedbackStore
    from apps.api.seawatch.main import create_app

    track, event, alert = _live_alert_fixture()
    feedback = FeedbackStore(None)
    runtime = LiveDetectionRuntime(
        VesselIdentityRegistry("stable-test-key"),
        component_factory=lambda: LiveDetectionComponents(
            analyzer=_StubAnalyzer(
                [AnalysisResult([event], [alert], n_tracks=1, n_analyzed=1)],
                [track],
            ),
            context=DetectionContext([], []),
            context_quality="historical",
            feedback=feedback,
        ),
        clock=_Clock(BASE + timedelta(minutes=11)),
    )
    runtime.update([_observation()], scanned_at=BASE + timedelta(minutes=10))
    monkeypatch.setattr(
        detection_api,
        "get_live_runtime",
        lambda: SimpleNamespace(live_detection=runtime),
        raising=False,
    )
    monkeypatch.setattr(
        detection_api,
        "get_service",
        lambda: (_ for _ in ()).throw(
            AssertionError("live feedback touched scenario service")
        ),
    )
    client = TestClient(create_app())

    status_response = client.post(
        f"/detection/alerts/{alert.id}/status?source=live",
        json={"status": "under_review", "note": "Checking live track"},
    )
    note_response = client.post(
        f"/detection/alerts/{alert.id}/notes?source=live",
        json={"text": "Cross-check requested"},
    )

    assert status_response.status_code == 200
    assert status_response.json()["status"] == "under_review"
    assert note_response.status_code == 200
    assert [note["text"] for note in note_response.json()["notes"]][-1] == (
        "Cross-check requested"
    )
    assert "416000001" not in status_response.text + note_response.text


def test_default_detection_routes_still_use_scenario_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from apps.api.seawatch.api import detection as detection_api

    calls: list[str] = []
    service = SimpleNamespace(meta=lambda: calls.append("meta") or {"name": "scenario"})
    monkeypatch.setattr(detection_api, "get_service", lambda: service)

    assert detection_api.scenario() == {"name": "scenario"}
    assert calls == ["meta"]
