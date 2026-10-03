from __future__ import annotations

from datetime import datetime, timezone

from apps.api.seawatch.live.resilience import (
    CoverageKind,
    DisplayState,
    EdgeInputKind,
    ObservationOrigin,
    OperatingMode,
    PowerMode,
    ResilienceStatus,
    SourceHealthSnapshot,
    SourceStatus,
)


def test_resilience_enums_have_stable_wire_values() -> None:
    assert [mode.value for mode in OperatingMode] == [
        "CLOUD_LIVE",
        "EDGE_LIVE",
        "EDGE_REPLAY",
        "NO_LIVE_SOURCE",
        "OFFLINE_DEMO",
    ]
    assert EdgeInputKind.UDP.value == "udp"
    assert EdgeInputKind.REPLAY.value == "replay"
    assert CoverageKind.CLOUD.value == "taiwan_wide_network_feed"
    assert CoverageKind.EDGE.value == "local_rf"
    assert CoverageKind.NONE.value == "none"
    assert CoverageKind.DEMO.value == "demo"
    assert ObservationOrigin.CLOUD.value == "cloud"
    assert ObservationOrigin.EDGE_RF.value == "edge_rf"
    assert ObservationOrigin.EDGE_REPLAY.value == "edge_replay"
    assert DisplayState.LIVE.value == "live"
    assert DisplayState.CACHED.value == "cached"
    assert DisplayState.STALE.value == "stale"
    assert PowerMode.EXTERNAL.value == "external"
    assert PowerMode.BATTERY_UPS.value == "battery_ups"


def test_health_contract_separates_raw_monotonic_input_from_public_status() -> None:
    observed = datetime(2026, 10, 1, tzinfo=timezone.utc)
    raw = SourceHealthSnapshot(
        source="open_waters",
        connected=True,
        last_message_at=observed,
        last_message_monotonic=125.5,
        vessel_count=42,
        input_kind=None,
    )
    public = SourceStatus(
        source=raw.source,
        fresh=True,
        message_age_seconds=2.5,
        vessel_count=raw.vessel_count,
        connected=raw.connected,
        input_kind=raw.input_kind,
    )
    status = ResilienceStatus(
        mode=OperatingMode.CLOUD_LIVE,
        coverage=CoverageKind.CLOUD,
        simulated=False,
        cloud=public,
        edge=SourceStatus(
            source="edge_ais",
            fresh=False,
            message_age_seconds=None,
            vessel_count=0,
            connected=False,
            input_kind=EdgeInputKind.DISABLED,
        ),
        power_mode=PowerMode.EXTERNAL,
    )

    assert raw.last_message_monotonic == 125.5
    assert status.cloud.fresh is True
    assert status.mode.value == "CLOUD_LIVE"
