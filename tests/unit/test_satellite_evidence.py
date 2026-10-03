from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from apps.api.seawatch.satellite.evidence import (
    SatelliteEvidence,
    satellite_evidence_from_stac,
)


def test_complete_stac_feature_maps_values_and_field_provenance() -> None:
    feature_collection = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "id": "S1A_SCENE_001",
                "properties": {
                    "platform": "sentinel-1a",
                    "datetime": "2026-09-30T02:15:00Z",
                    "orbit": 12345,
                },
            }
        ],
    }

    evidence = satellite_evidence_from_stac(feature_collection)

    assert evidence == [
        SatelliteEvidence(
            provider="Sentinel-1 STAC",
            scene_id="S1A_SCENE_001",
            platform="sentinel-1a",
            datetime="2026-09-30T02:15:00Z",
            orbit=12345,
            availability="Available",
            provenance={
                "scene_id": "Observed",
                "platform": "Observed",
                "datetime": "Observed",
                "orbit": "Observed",
                "availability": "Derived",
            },
        )
    ]


def test_missing_fields_are_unknown_without_using_fallback_fields() -> None:
    features = [
        {
            "type": "Feature",
            "properties": {
                "constellation": "sentinel-1",
                "start_datetime": "2026-09-30T02:15:00Z",
                "sat:relative_orbit": 87,
            },
        }
    ]

    evidence = satellite_evidence_from_stac(features)

    assert evidence[0].scene_id == "Unknown"
    assert evidence[0].platform == "Unknown"
    assert evidence[0].datetime == "Unknown"
    assert evidence[0].orbit == "Unknown"
    assert evidence[0].availability == "Available"
    assert evidence[0].provenance == {
        "scene_id": "Unknown",
        "platform": "Unknown",
        "datetime": "Unknown",
        "orbit": "Unknown",
        "availability": "Derived",
    }


def test_zero_coverage_returns_one_unknown_evidence() -> None:
    evidence = satellite_evidence_from_stac(
        {"type": "FeatureCollection", "features": []}
    )

    assert evidence == [
        SatelliteEvidence(
            provider="Sentinel-1 STAC",
            scene_id="Unknown",
            platform="Unknown",
            datetime="Unknown",
            orbit="Unknown",
            availability="Unknown",
            provenance={
                "scene_id": "Unknown",
                "platform": "Unknown",
                "datetime": "Unknown",
                "orbit": "Unknown",
                "availability": "Unknown",
            },
        )
    ]


def test_multiple_scenes_produce_one_evidence_per_feature_in_input_order() -> None:
    features = [
        {"id": "scene-a", "properties": {"platform": "sentinel-1a"}},
        {"id": "scene-b", "properties": {"platform": "sentinel-1b"}},
    ]

    evidence = satellite_evidence_from_stac(features)

    assert [item.scene_id for item in evidence] == ["scene-a", "scene-b"]
    assert [item.platform for item in evidence] == ["sentinel-1a", "sentinel-1b"]


def test_same_input_produces_same_output_without_mutating_input() -> None:
    feature_collection = {
        "type": "FeatureCollection",
        "features": [
            {
                "id": "scene-a",
                "properties": {
                    "platform": "sentinel-1a",
                    "datetime": "2026-09-30T02:15:00Z",
                    "orbit": 12345,
                },
            }
        ],
    }
    original = {
        "type": "FeatureCollection",
        "features": [
            {
                "id": "scene-a",
                "properties": {
                    "platform": "sentinel-1a",
                    "datetime": "2026-09-30T02:15:00Z",
                    "orbit": 12345,
                },
            }
        ],
    }

    first = satellite_evidence_from_stac(feature_collection)
    second = satellite_evidence_from_stac(feature_collection)

    assert first == second
    assert feature_collection == original


def test_satellite_evidence_is_frozen() -> None:
    evidence = satellite_evidence_from_stac([])[0]

    with pytest.raises(FrozenInstanceError):
        evidence.availability = "Available"  # type: ignore[misc]
