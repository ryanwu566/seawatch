"""Provenance-typed data schemas for the Historical AIS ingestion pipeline.

Design rules
------------
* Every field that can be unknown is wrapped in ``Provenanced``.
  ``Provenanced.value is None`` always implies ``provenance == "unknown"``.

* ``data_source`` on ``HistoricalAisRecord`` is always a non-empty string that
  must be verified before the record enters any pipeline:

  - ``"synthetic_fixture"``
      Deterministic test/demo data; never real AIS.

  - ``"noaa_marinecadastre"``
      NOAA MarineCadastre historical AIS.

  - ``"nodass"``
      NODASS / Taiwan AIS.

  - ``"gfw_presence"``
      Global Fishing Watch AIS Vessel Presence.
      This is standardized historical presence data, not raw AIS messages.

* No MMSI or other identifying field is exposed on ``VesselBaseline``.
  ``vessel_key`` is always the HMAC-derived opaque identifier used throughout
  the live layer.

* The raw ``vessel_id`` inside ``HistoricalAisRecord`` is pipeline-internal
  only and must not appear in public API responses.

* No threat/anomaly vocabulary is used in baseline output.
  ``VesselBaseline`` describes what is typical for a vessel using historical
  movement geometry and descriptive statistics for human review.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


# --------------------------------------------------------------------------- #
# Provenance vocabulary
# --------------------------------------------------------------------------- #

Provenance = Literal[
    "official",
    "observed",
    "derived",
    "unknown",
]

Confidence = Literal[
    "HIGH",
    "MEDIUM",
    "LOW",
]


# --------------------------------------------------------------------------- #
# Recognized historical data sources
# --------------------------------------------------------------------------- #

DATA_SOURCE_SYNTHETIC: str = "synthetic_fixture"

DATA_SOURCE_NOAA: str = "noaa_marinecadastre"

DATA_SOURCE_NODASS: str = "nodass"

DATA_SOURCE_GFW_PRESENCE: str = "gfw_presence"


# --------------------------------------------------------------------------- #
# Sufficiency thresholds
# --------------------------------------------------------------------------- #

MIN_HISTORY_DAYS: int = 3
"""Minimum distinct observed days before a baseline is considered sufficient."""

MIN_HISTORY_TRACKS: int = 5
"""Minimum per-route contributing tracks."""

MIN_TRACK_POINTS: int = 3
"""Minimum positions in a single track."""


# --------------------------------------------------------------------------- #
# Raw record — adapter output
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class HistoricalAisRecord:
    """One historical vessel-position observation.

    This is the canonical type produced by every ``HistoricalAisAdapter``.
    Downstream pipeline code only reads ``HistoricalAisRecord`` and does not
    depend on source-specific schemas.

    All coordinates are WGS84 / EPSG:4326.

    ``vessel_id`` is a source-specific vessel identifier used internally to
    group historical observations.

    Examples:
    - NOAA: MMSI or another canonicalized source identifier.
    - GFW: Global Fishing Watch ``vesselId``.

    The raw ``vessel_id`` must never appear in public API responses or
    persisted public-facing evidence artifacts.

    ``observed_at`` is an ISO-8601 UTC timestamp.

    For Global Fishing Watch Vessel Presence, ``observed_at`` represents the
    standardized presence observation time. It must not be interpreted as an
    exact raw AIS transmission timestamp.

    ``data_source`` must equal a recognized ``DATA_SOURCE_*`` constant.
    """

    vessel_id: str
    """Pipeline-internal vessel identifier."""

    observed_at: str
    """ISO-8601 UTC timestamp of the historical observation."""

    longitude: float

    latitude: float

    data_source: str
    """Recognized historical data-source label."""

    sog_knots: float | None = None

    cog_deg: float | None = None

    heading_deg: float | None = None

    vessel_type: int | None = None
    """Coarse AIS ship-and-cargo type code when known.

    GFW textual vessel classifications are intentionally not converted into
    numeric AIS ship-type codes.
    """

    mmsi: int | None = field(
        default=None,
        repr=False,
        compare=False,
    )
    """Internal identity input used only for the shared live/history join.

    This value must never be copied into a public baseline or API payload.
    ``repr=False`` and ``compare=False`` reduce accidental disclosure and keep
    record equality focused on the canonical historical observation contract.
    """

    def is_synthetic(self) -> bool:
        """Return True when this record comes from synthetic fixture data."""

        return self.data_source == DATA_SOURCE_SYNTHETIC


# --------------------------------------------------------------------------- #
# Provenanced value wrapper
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Provenanced:
    """A value plus information describing how it is known.

    ``value is None`` always requires ``provenance == "unknown"``.
    """

    value: object

    provenance: Provenance

    note: str | None = None

    def __post_init__(self) -> None:
        if (
            self.value is None
            and self.provenance != "unknown"
        ):
            raise ValueError(
                "Provenanced: value is None but provenance is not 'unknown'"
            )

    def to_dict(self) -> dict:
        out: dict = {
            "value": self.value,
            "provenance": self.provenance,
        }

        if self.note is not None:
            out["note"] = self.note

        return out


# --------------------------------------------------------------------------- #
# Baseline output — Product 1
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class VesselHistorySummary:
    """When this vessel was observed and how many observations exist."""

    observed_day_count: Provenanced

    first_observed_utc: Provenanced

    last_observed_utc: Provenanced

    total_observations: Provenanced

    data_source: str


# --------------------------------------------------------------------------- #
# Baseline output — Product 2
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class TypicalRoute:
    """One recurring historical movement corridor."""

    route_key: str
    """Neutral route grouping key such as ``<areaA>-><areaB>``."""

    occurrence_count: int

    corridor_centerline: tuple[
        tuple[float, float],
        ...
    ]
    """Sequence of ``(longitude, latitude)`` pairs."""

    corridor_width_p90_m: Provenanced

    provenance: Provenance


# --------------------------------------------------------------------------- #
# Baseline output — Product 3
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class UsualOperatingArea:
    """Named maritime area where the vessel is regularly observed."""

    area_id: str

    label_en: str

    label_zh: str

    dwell_fraction: Provenanced
    """Fraction of historical observations inside this area."""


# --------------------------------------------------------------------------- #
# Complete vessel baseline
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class VesselBaseline:
    """Per-vessel historical movement baseline.

    The baseline answers:

        "What is typical for this vessel?"

    It contains historical movement geometry and descriptive statistics only.

    It is not:
    - a threat score,
    - an intent prediction,
    - an authorization decision,
    - a legality judgement.

    ``sufficient=False`` means there is not enough historical evidence to
    construct a reliable baseline.

    Downstream callers must return Unknown rather than fabricate a result.

    ``vessel_key`` is an opaque identifier. Raw source identifiers such as
    MMSI or GFW vesselId must never be exposed in this artifact.
    """

    schema_version: str = "vessel-baseline-1"


    # --------------------------------------------------------------------- #
    # Identity
    # --------------------------------------------------------------------- #

    vessel_key: str = ""
    """Opaque vessel identifier."""


    # --------------------------------------------------------------------- #
    # Product 1 — history summary
    # --------------------------------------------------------------------- #

    history_summary: VesselHistorySummary = field(
        default_factory=lambda: VesselHistorySummary(
            observed_day_count=Provenanced(
                None,
                "unknown",
            ),
            first_observed_utc=Provenanced(
                None,
                "unknown",
            ),
            last_observed_utc=Provenanced(
                None,
                "unknown",
            ),
            total_observations=Provenanced(
                None,
                "unknown",
            ),
            data_source="unknown",
        )
    )


    # --------------------------------------------------------------------- #
    # Product 2 — typical routes
    # --------------------------------------------------------------------- #

    typical_routes: tuple[
        TypicalRoute,
        ...
    ] = ()


    # --------------------------------------------------------------------- #
    # Product 3 — usual operating areas
    # --------------------------------------------------------------------- #

    usual_operating_areas: tuple[
        UsualOperatingArea,
        ...
    ] = ()


    # --------------------------------------------------------------------- #
    # Product 4 — historical track count
    # --------------------------------------------------------------------- #

    historical_track_count: int = 0


    # --------------------------------------------------------------------- #
    # Product 5 — confidence
    # --------------------------------------------------------------------- #

    confidence: Provenanced = field(
        default_factory=lambda: Provenanced(
            None,
            "unknown",
        )
    )


    # --------------------------------------------------------------------- #
    # Sufficiency
    # --------------------------------------------------------------------- #

    sufficient: bool = False


    # --------------------------------------------------------------------- #
    # Documented thresholds
    # --------------------------------------------------------------------- #

    thresholds_used: dict = field(
        default_factory=lambda: {
            "min_history_days": MIN_HISTORY_DAYS,
            "min_history_tracks": MIN_HISTORY_TRACKS,
            "min_track_points": MIN_TRACK_POINTS,
        }
    )


    # --------------------------------------------------------------------- #
    # Source provenance
    # --------------------------------------------------------------------- #

    data_source: str = "unknown"


    disclaimer: str = (
        "Per-vessel historical baseline for human review only. "
        "A derived summary of this vessel's own past movement patterns, "
        "not a judgement about the vessel, its intent, or its authorization."
    )


    # --------------------------------------------------------------------- #
    # Serialization
    # --------------------------------------------------------------------- #

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,

            "vessel_key": self.vessel_key,

            "history_summary": {
                "observed_day_count":
                    self.history_summary.observed_day_count.to_dict(),

                "first_observed_utc":
                    self.history_summary.first_observed_utc.to_dict(),

                "last_observed_utc":
                    self.history_summary.last_observed_utc.to_dict(),

                "total_observations":
                    self.history_summary.total_observations.to_dict(),

                "data_source":
                    self.history_summary.data_source,
            },

            "typical_routes": [
                {
                    "route_key":
                        route.route_key,

                    "occurrence_count":
                        route.occurrence_count,

                    "corridor_centerline":
                        list(
                            route.corridor_centerline
                        ),

                    "corridor_width_p90_m":
                        route.corridor_width_p90_m.to_dict(),

                    "provenance":
                        route.provenance,
                }
                for route in self.typical_routes
            ],

            "usual_operating_areas": [
                {
                    "area_id":
                        area.area_id,

                    "label_en":
                        area.label_en,

                    "label_zh":
                        area.label_zh,

                    "dwell_fraction":
                        area.dwell_fraction.to_dict(),
                }
                for area in self.usual_operating_areas
            ],

            "historical_track_count":
                self.historical_track_count,

            "confidence":
                self.confidence.to_dict(),

            "sufficient":
                self.sufficient,

            "thresholds_used":
                self.thresholds_used,

            "data_source":
                self.data_source,

            "disclaimer":
                self.disclaimer,
        }
