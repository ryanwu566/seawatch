from __future__ import annotations

import json
from dataclasses import FrozenInstanceError, dataclass
from types import MappingProxyType

import pytest
from fastapi.encoders import jsonable_encoder

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


def test_to_dict_returns_the_strict_json_safe_public_schema() -> None:
    evidence = satellite_evidence_from_stac(
        [
            {
                "id": "S1A_SCENE_001",
                "properties": {
                    "platform": "sentinel-1a",
                    "datetime": "2026-09-30T02:15:00Z",
                    "orbit": 12345,
                },
            }
        ]
    )[0]

    payload = evidence.to_dict()

    assert payload == {
        "provider": "Sentinel-1 STAC",
        "scene_id": "S1A_SCENE_001",
        "platform": "sentinel-1a",
        "datetime": "2026-09-30T02:15:00Z",
        "orbit": 12345,
        "availability": "Available",
        "provenance": {
            "scene_id": "Observed",
            "platform": "Observed",
            "datetime": "Observed",
            "orbit": "Observed",
            "availability": "Derived",
        },
    }
    assert not isinstance(payload["provenance"], MappingProxyType)
    assert jsonable_encoder(payload) == payload
    assert json.loads(json.dumps(payload, allow_nan=False)) == payload


def test_to_dict_whitelists_provenance_fields() -> None:
    evidence = SatelliteEvidence(
        provider="Sentinel-1 STAC",
        scene_id="scene-a",
        platform="sentinel-1a",
        datetime="2026-09-30T02:15:00Z",
        orbit=12345,
        availability="Available",
        provenance={
            "scene_id": "Observed",
            "availability": "Derived",
            "mmsi": "Observed",
            "secret": "Observed",
        },  # type: ignore[dict-item]
    )

    assert evidence.to_dict()["provenance"] == {
        "scene_id": "Observed",
        "availability": "Derived",
    }


def test_to_dict_rejects_non_schema_values_in_supported_fields() -> None:
    @dataclass(frozen=True)
    class PrivateSourceValue:
        secret: str

    evidence = SatelliteEvidence(
        provider="Sentinel-1 STAC",
        scene_id=MappingProxyType({"mmsi": "416000001"}),
        platform=PrivateSourceValue(secret="source-secret"),
        datetime=["source-token"],
        orbit=float("nan"),
        availability="Available",
        provenance={
            "scene_id": "Observed",
            "platform": "Observed",
            "datetime": "Observed",
            "orbit": "Observed",
            "availability": "Derived",
        },
    )  # type: ignore[arg-type]

    payload = evidence.to_dict()

    assert payload["scene_id"] == "Unknown"
    assert payload["platform"] == "Unknown"
    assert payload["datetime"] == "Unknown"
    assert payload["orbit"] == "Unknown"
    assert payload["provenance"] == {
        "scene_id": "Unknown",
        "platform": "Unknown",
        "datetime": "Unknown",
        "orbit": "Unknown",
        "availability": "Derived",
    }
    serialized = json.dumps(payload, allow_nan=False)
    for private_value in ("416000001", "source-secret", "source-token"):
        assert private_value not in serialized


def test_unrecognized_stac_metadata_never_expands_serialized_schema() -> None:
    private_values = {
        "mmsi": "416000001",
        "MMSI": "416000002",
        "vessel_id": "raw-vessel-id",
        "vesselId": "rawVesselId",
        "provider_id": "provider-vessel-key",
        "imo": "IMO1234567",
        "callsign": "SECRET-CALLSIGN",
        "ship_name": "PRIVATE SHIP",
        "vessel_name": "PRIVATE VESSEL",
        "secret": "source-secret",
        "token": "source-token",
        "api_key": "source-api-key",
        "href": "https://example.test/private-item.json",
        "arbitrary_unknown_property": "must-not-pass-through",
    }
    feature = {
        "id": "scene-safe",
        **private_values,
        "assets": {
            "thumbnail": {"href": "https://example.test/private-asset.png"}
        },
        "properties": {
            "platform": "sentinel-1a",
            "datetime": "2026-09-30T02:15:00Z",
            "orbit": 12345,
            **private_values,
            "assets": {
                "visual": {"href": "https://example.test/private-visual.tif"}
            },
        },
    }

    payload = satellite_evidence_from_stac([feature])[0].to_dict()
    serialized = json.dumps(payload, sort_keys=True)

    assert set(payload) == {
        "provider",
        "scene_id",
        "platform",
        "datetime",
        "orbit",
        "availability",
        "provenance",
    }
    assert set(payload["provenance"]) == {
        "scene_id",
        "platform",
        "datetime",
        "orbit",
        "availability",
    }
    for forbidden_key in (*private_values, "assets"):
        assert forbidden_key not in payload
        assert forbidden_key not in payload["provenance"]
    for forbidden_value in (
        *private_values.values(),
        "https://example.test/private-asset.png",
        "https://example.test/private-visual.tif",
    ):
        assert forbidden_value not in serialized


def test_explicit_unknown_evidence_serializes_without_collapsing_to_no_evidence() -> None:
    evidence = satellite_evidence_from_stac(
        {"type": "FeatureCollection", "features": []}
    )

    assert [item.to_dict() for item in evidence] == [
        {
            "provider": "Sentinel-1 STAC",
            "scene_id": "Unknown",
            "platform": "Unknown",
            "datetime": "Unknown",
            "orbit": "Unknown",
            "availability": "Unknown",
            "provenance": {
                "scene_id": "Unknown",
                "platform": "Unknown",
                "datetime": "Unknown",
                "orbit": "Unknown",
                "availability": "Unknown",
            },
        }
    ]


def test_serialized_output_is_deterministic() -> None:
    source = [
        {
            "id": "scene-a",
            "properties": {
                "platform": "sentinel-1a",
                "datetime": "2026-09-30T02:15:00Z",
                "orbit": 12345,
            },
        }
    ]

    first = satellite_evidence_from_stac(source)[0].to_dict()
    second = satellite_evidence_from_stac(source)[0].to_dict()

    assert first == second
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
