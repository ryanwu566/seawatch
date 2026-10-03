"""Pure conversion from STAC metadata to satellite evidence records."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from math import isfinite
from types import MappingProxyType
from typing import Any, Literal, TypeAlias

EvidenceValue: TypeAlias = str | int | float | bool
ProvenanceValue: TypeAlias = Literal["Observed", "Derived", "Unknown"]

_PROVIDER = "Sentinel-1 STAC"
_UNKNOWN = "Unknown"
_SOURCE_FIELDS = ("scene_id", "platform", "datetime", "orbit")


def _is_evidence_value(value: object) -> bool:
    if isinstance(value, (str, bool, int)):
        return True
    return isinstance(value, float) and isfinite(value)


def _evidence_value_or_unknown(value: object) -> EvidenceValue:
    if isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float) and isfinite(value):
        return value
    return _UNKNOWN


def _provenance_or_unknown(value: object) -> ProvenanceValue:
    if not isinstance(value, str):
        return "Unknown"
    if value == "Observed":
        return "Observed"
    if value == "Derived":
        return "Derived"
    if value == "Unknown":
        return "Unknown"
    return "Unknown"


@dataclass(frozen=True)
class SatelliteEvidence:
    """Metadata for one satellite scene with field-level provenance."""

    provider: str
    scene_id: EvidenceValue
    platform: EvidenceValue
    datetime: EvidenceValue
    orbit: EvidenceValue
    availability: EvidenceValue
    provenance: Mapping[str, ProvenanceValue]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "provenance",
            MappingProxyType(dict(self.provenance)),
        )

    def to_dict(self) -> dict[str, object]:
        """Return the explicit, JSON-safe public evidence representation."""

        provenance_fields = (*_SOURCE_FIELDS, "availability")
        raw_values = {
            "provider": self.provider,
            "scene_id": self.scene_id,
            "platform": self.platform,
            "datetime": self.datetime,
            "orbit": self.orbit,
            "availability": self.availability,
        }
        values = {
            field: _evidence_value_or_unknown(value)
            for field, value in raw_values.items()
        }
        return {
            **values,
            "provenance": {
                field: (
                    _provenance_or_unknown(self.provenance[field])
                    if _is_evidence_value(raw_values[field])
                    else "Unknown"
                )
                for field in provenance_fields
                if field in self.provenance
            },
        }


def satellite_evidence_from_stac(
    feature_collection_or_features: Mapping[str, Any]
    | Iterable[Mapping[str, Any]],
) -> list[SatelliteEvidence]:
    """Convert a STAC FeatureCollection or feature iterable without I/O."""

    if isinstance(feature_collection_or_features, Mapping):
        features = feature_collection_or_features.get("features", ())
    else:
        features = feature_collection_or_features

    feature_list = list(features)
    if not feature_list:
        return [_unknown_evidence()]

    return [_evidence_from_feature(feature) for feature in feature_list]


def _evidence_from_feature(feature: Mapping[str, Any]) -> SatelliteEvidence:
    properties = feature.get("properties")
    if not isinstance(properties, Mapping):
        properties = {}

    raw_values = {
        "scene_id": feature.get("id"),
        "platform": properties.get("platform"),
        "datetime": properties.get("datetime"),
        "orbit": properties.get("orbit"),
    }
    values = {
        field: _evidence_value_or_unknown(value)
        for field, value in raw_values.items()
    }
    provenance: dict[str, ProvenanceValue] = {
        field: "Observed" if _is_evidence_value(raw_values[field]) else "Unknown"
        for field in _SOURCE_FIELDS
    }
    provenance["availability"] = "Derived"

    return SatelliteEvidence(
        provider=_PROVIDER,
        scene_id=values["scene_id"],
        platform=values["platform"],
        datetime=values["datetime"],
        orbit=values["orbit"],
        availability="Available",
        provenance=provenance,
    )


def _unknown_evidence() -> SatelliteEvidence:
    provenance: dict[str, ProvenanceValue] = {
        field: "Unknown" for field in (*_SOURCE_FIELDS, "availability")
    }
    return SatelliteEvidence(
        provider=_PROVIDER,
        scene_id=_UNKNOWN,
        platform=_UNKNOWN,
        datetime=_UNKNOWN,
        orbit=_UNKNOWN,
        availability=_UNKNOWN,
        provenance=provenance,
    )
