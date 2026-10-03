from __future__ import annotations


def test_gfw_presence_is_a_recognized_historical_source() -> None:
    from apps.api.seawatch.historical.schema import DATA_SOURCE_GFW_PRESENCE

    assert DATA_SOURCE_GFW_PRESENCE == "gfw_presence"


def test_internal_mmsi_is_excluded_from_record_repr_and_equality() -> None:
    from apps.api.seawatch.historical.schema import HistoricalAisRecord

    common = {
        "vessel_id": "gfw-vessel-1",
        "observed_at": "2026-09-01T08:00:00Z",
        "longitude": 119.59,
        "latitude": 25.8,
        "data_source": "gfw_presence",
    }
    first = HistoricalAisRecord(**common, mmsi=416000001)
    second = HistoricalAisRecord(**common, mmsi=416000002)

    assert first == second
    assert "mmsi" not in repr(first).lower()
    assert "416000001" not in repr(first)


def test_public_baseline_serialization_has_no_source_identifiers() -> None:
    from apps.api.seawatch.historical.schema import VesselBaseline

    payload = VesselBaseline(vessel_key="v_opaque").to_dict()
    serialized_keys = str(payload).casefold()

    for forbidden in ("mmsi", "imo", "callsign", "shipname", "vesselid"):
        assert forbidden not in serialized_keys
