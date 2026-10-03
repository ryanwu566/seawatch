"""Build privacy-safe per-vessel baselines from historical GFW presence data.

Global Fishing Watch Vessel Presence contains hourly standardized presence
observations, not raw AIS messages. The 7,200-second segmentation threshold in
``config/gfw_presence_features_v1.json`` is an engineering rule for that hourly
product only.

The current repository has no defensible origin/destination clustering or
named operating-area definition. Consequently all qualifying segments for one
vessel are summarized as one explicitly named ``historical-cohort``. Usual
operating areas remain empty instead of being invented.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import pandas as pd

from ..trajectories.contracts import (
    PHASE1_COLUMNS,
    FeatureConfig,
    load_feature_config,
    validate_observations,
)
from ..trajectories.route_deviation import build_route_baseline
from ..trajectories.segmentation import segment_observations
from .schema import (
    DATA_SOURCE_GFW_PRESENCE,
    MIN_HISTORY_DAYS,
    MIN_HISTORY_TRACKS,
    MIN_TRACK_POINTS,
    HistoricalAisRecord,
    Provenanced,
    TypicalRoute,
    VesselBaseline,
    VesselHistorySummary,
)


GFW_FEATURE_CONFIG_PATH = (
    Path(__file__).resolve().parents[4] / "config" / "gfw_presence_features_v1.json"
)

HISTORICAL_COHORT_ROUTE_KEY = "historical-cohort"
"""Neutral label for the one all-segments cohort; it is not OD clustering."""


def _validate_vessel_key(vessel_key: str) -> None:
    if not vessel_key or not vessel_key.startswith("v_"):
        raise ValueError("vessel_key must be a non-empty opaque v_ identifier")


def historical_records_to_phase1(
    records: Iterable[HistoricalAisRecord],
    *,
    vessel_key: str,
) -> pd.DataFrame:
    """Convert canonical records to the existing Phase 1 observation contract.

    Only the opaque vessel key enters ``track_id``. Source identifiers and the
    internal MMSI are intentionally absent from the returned frame.
    """

    _validate_vessel_key(vessel_key)

    rows = [
        {
            "track_id": vessel_key,
            "base_date_time": record.observed_at,
            "longitude": record.longitude,
            "latitude": record.latitude,
            "sog": record.sog_knots,
            "cog": record.cog_deg,
            "heading": record.heading_deg,
            "vessel_type": record.vessel_type,
        }
        for record in records
    ]
    return pd.DataFrame(rows, columns=PHASE1_COLUMNS)


def _history_summary(
    frame: pd.DataFrame,
    *,
    data_source: str,
) -> VesselHistorySummary:
    if frame.empty:
        return VesselHistorySummary(
            observed_day_count=Provenanced(None, "unknown"),
            first_observed_utc=Provenanced(None, "unknown"),
            last_observed_utc=Provenanced(None, "unknown"),
            total_observations=Provenanced(None, "unknown"),
            data_source=data_source,
        )

    timestamps = frame["base_date_time"]
    first = timestamps.iloc[0].isoformat().replace("+00:00", "Z")
    last = timestamps.iloc[-1].isoformat().replace("+00:00", "Z")
    return VesselHistorySummary(
        observed_day_count=Provenanced(
            int(timestamps.dt.date.nunique()),
            "derived",
        ),
        first_observed_utc=Provenanced(first, "observed"),
        last_observed_utc=Provenanced(last, "observed"),
        total_observations=Provenanced(len(frame), "derived"),
        data_source=data_source,
    )


def _unknown_baseline(
    vessel_key: str,
    *,
    data_source: str,
    summary: VesselHistorySummary,
    track_count: int,
    reason: str,
) -> VesselBaseline:
    return VesselBaseline(
        vessel_key=vessel_key,
        history_summary=summary,
        historical_track_count=track_count,
        confidence=Provenanced(None, "unknown", reason),
        sufficient=False,
        data_source=data_source,
    )


def build_vessel_baseline(
    vessel_key: str,
    records: Iterable[HistoricalAisRecord],
    *,
    feature_config: FeatureConfig | None = None,
) -> VesselBaseline:
    """Build one per-vessel historical cohort using existing trajectory code."""

    _validate_vessel_key(vessel_key)
    materialized = list(records)
    if not materialized:
        summary = _history_summary(
            pd.DataFrame(columns=PHASE1_COLUMNS),
            data_source=DATA_SOURCE_GFW_PRESENCE,
        )
        return _unknown_baseline(
            vessel_key,
            data_source=DATA_SOURCE_GFW_PRESENCE,
            summary=summary,
            track_count=0,
            reason="no historical observations",
        )

    sources = {record.data_source for record in materialized}
    if sources != {DATA_SOURCE_GFW_PRESENCE}:
        raise ValueError(
            "GFW historical baseline requires data_source='gfw_presence'"
        )

    config = feature_config or load_feature_config(GFW_FEATURE_CONFIG_PATH)
    phase1 = historical_records_to_phase1(materialized, vessel_key=vessel_key)
    validated = validate_observations(phase1).frame
    summary = _history_summary(validated, data_source=DATA_SOURCE_GFW_PRESENCE)
    segmented = segment_observations(validated, config)

    tracks: list[list[tuple[float, float]]] = []
    for _, segment in segmented.observations.groupby("segment_id", sort=False):
        if len(segment) < MIN_TRACK_POINTS:
            continue
        tracks.append(
            list(
                zip(
                    segment["longitude"].astype(float),
                    segment["latitude"].astype(float),
                    strict=True,
                )
            )
        )

    track_count = len(tracks)
    observed_day_count = int(summary.observed_day_count.value or 0)
    first = str(summary.first_observed_utc.value)
    last = str(summary.last_observed_utc.value)
    route_baseline = build_route_baseline(
        HISTORICAL_COHORT_ROUTE_KEY,
        tracks,
        observed_time_range=f"{first}/{last}",
        min_tracks=MIN_HISTORY_TRACKS,
    )

    insufficient_reasons: list[str] = []
    if observed_day_count < MIN_HISTORY_DAYS:
        insufficient_reasons.append(
            f"requires at least {MIN_HISTORY_DAYS} observed days"
        )
    if track_count < MIN_HISTORY_TRACKS:
        insufficient_reasons.append(
            f"requires at least {MIN_HISTORY_TRACKS} qualifying tracks"
        )
    if not route_baseline.sufficient:
        insufficient_reasons.append("historical cohort corridor is insufficient")

    if insufficient_reasons:
        return _unknown_baseline(
            vessel_key,
            data_source=DATA_SOURCE_GFW_PRESENCE,
            summary=summary,
            track_count=track_count,
            reason="; ".join(insufficient_reasons),
        )

    corridor_width = route_baseline.source().corridor_width_p90_m
    route = TypicalRoute(
        route_key=HISTORICAL_COHORT_ROUTE_KEY,
        occurrence_count=route_baseline.contributing_track_count,
        corridor_centerline=route_baseline.centerline,
        corridor_width_p90_m=Provenanced(
            corridor_width,
            "derived",
            (
                "P90 width across one per-vessel all-segments historical "
                "cohort; origin/destination routes are not clustered."
            ),
        ),
        provenance="derived",
    )
    confidence = "HIGH" if track_count >= 2 * MIN_HISTORY_TRACKS else "MEDIUM"
    return VesselBaseline(
        vessel_key=vessel_key,
        history_summary=summary,
        typical_routes=(route,),
        usual_operating_areas=(),
        historical_track_count=track_count,
        confidence=Provenanced(confidence, "derived"),
        sufficient=True,
        data_source=DATA_SOURCE_GFW_PRESENCE,
    )
