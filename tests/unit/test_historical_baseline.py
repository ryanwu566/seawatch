from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from apps.api.seawatch.historical.schema import HistoricalAisRecord


def _record(
    observed_at: datetime,
    *,
    vessel_id: str = "raw-gfw-vessel-id",
    longitude: float = 120.0,
    latitude: float = 22.0,
    mmsi: int | None = 416000001,
) -> HistoricalAisRecord:
    return HistoricalAisRecord(
        vessel_id=vessel_id,
        observed_at=observed_at.isoformat().replace("+00:00", "Z"),
        longitude=longitude,
        latitude=latitude,
        data_source="gfw_presence",
        mmsi=mmsi,
    )


def _daily_tracks(day_count: int) -> list[HistoricalAisRecord]:
    start = datetime(2026, 9, 1, tzinfo=timezone.utc)
    records: list[HistoricalAisRecord] = []
    for day in range(day_count):
        for hour in range(3):
            records.append(
                _record(
                    start + timedelta(days=day, hours=hour),
                    longitude=120.0 + 0.1 * hour,
                    latitude=22.0 + 0.0002 * (day % 2),
                )
            )
    return records


def test_historical_records_convert_to_exact_phase1_contract_with_unknown_navigation() -> None:
    from apps.api.seawatch.historical.baseline import historical_records_to_phase1
    from apps.api.seawatch.trajectories.contracts import PHASE1_COLUMNS

    frame = historical_records_to_phase1(
        [_record(datetime(2026, 9, 1, tzinfo=timezone.utc))],
        vessel_key="v_opaque",
    )

    assert frame.columns.tolist() == list(PHASE1_COLUMNS)
    assert frame.loc[0, "track_id"] == "v_opaque"
    assert pd.isna(frame.loc[0, "sog"])
    assert pd.isna(frame.loc[0, "cog"])
    assert pd.isna(frame.loc[0, "heading"])
    assert pd.isna(frame.loc[0, "vessel_type"])
    assert "mmsi" not in frame.columns
    assert "raw-gfw-vessel-id" not in frame.to_string()


def test_empty_history_still_rejects_a_non_opaque_vessel_key() -> None:
    from apps.api.seawatch.historical.baseline import build_vessel_baseline

    with pytest.raises(ValueError, match="opaque"):
        build_vessel_baseline("416000001", [])


def test_hourly_gfw_observations_do_not_split_at_7200_second_boundary() -> None:
    from apps.api.seawatch.historical.baseline import build_vessel_baseline

    start = datetime(2026, 9, 1, tzinfo=timezone.utc)
    records = [_record(start + timedelta(hours=offset)) for offset in (0, 2, 4)]

    baseline = build_vessel_baseline("v_opaque", records)

    assert baseline.historical_track_count == 1


def test_gap_greater_than_7200_seconds_creates_a_new_historical_track() -> None:
    from apps.api.seawatch.historical.baseline import build_vessel_baseline

    start = datetime(2026, 9, 1, tzinfo=timezone.utc)
    offsets = (0, 1, 2, 5, 6, 7)
    records = [_record(start + timedelta(hours=offset)) for offset in offsets]

    baseline = build_vessel_baseline("v_opaque", records)

    assert baseline.historical_track_count == 2


def test_invalid_canonical_coordinates_fail_at_phase1_validation() -> None:
    from apps.api.seawatch.historical.baseline import build_vessel_baseline

    records = _daily_tracks(3)
    records[0] = _record(
        datetime(2026, 9, 1, tzinfo=timezone.utc),
        longitude=181.0,
    )

    with pytest.raises(ValueError, match="coordinates"):
        build_vessel_baseline("v_opaque", records)


def test_insufficient_history_returns_unknown_without_fabricating_a_corridor() -> None:
    from apps.api.seawatch.historical.baseline import build_vessel_baseline

    baseline = build_vessel_baseline("v_opaque", _daily_tracks(2))

    assert baseline.sufficient is False
    assert baseline.confidence.value is None
    assert baseline.confidence.provenance == "unknown"
    assert baseline.typical_routes == ()
    assert baseline.usual_operating_areas == ()
    assert baseline.historical_track_count == 2
    assert baseline.data_source == "gfw_presence"


def test_sufficient_history_builds_one_explicit_historical_cohort() -> None:
    from apps.api.seawatch.historical.baseline import (
        HISTORICAL_COHORT_ROUTE_KEY,
        build_vessel_baseline,
    )

    baseline = build_vessel_baseline("v_opaque", _daily_tracks(5))

    assert baseline.sufficient is True
    assert baseline.confidence.value == "MEDIUM"
    assert baseline.historical_track_count == 5
    assert baseline.usual_operating_areas == ()
    assert len(baseline.typical_routes) == 1
    cohort = baseline.typical_routes[0]
    assert cohort.route_key == HISTORICAL_COHORT_ROUTE_KEY == "historical-cohort"
    assert cohort.occurrence_count == 5
    assert len(cohort.corridor_centerline) == 50
    assert cohort.corridor_width_p90_m.provenance == "derived"


def test_serialized_historical_cohort_never_exposes_internal_identifiers() -> None:
    from apps.api.seawatch.historical.baseline import build_vessel_baseline

    payload = build_vessel_baseline("v_opaque", _daily_tracks(5)).to_dict()
    serialized = str(payload).casefold()

    assert payload["vessel_key"] == "v_opaque"
    assert "raw-gfw-vessel-id" not in serialized
    assert "416000001" not in serialized
    for forbidden in ("mmsi", "imo", "callsign", "shipname", "vesselid"):
        assert forbidden not in serialized
