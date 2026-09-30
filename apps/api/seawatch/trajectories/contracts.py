"""Validated contracts for deterministic trajectory feature generation."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, fields
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd


PHASE1_COLUMNS = (
    "track_id",
    "base_date_time",
    "longitude",
    "latitude",
    "sog",
    "cog",
    "heading",
    "vessel_type",
)

FORBIDDEN_PUBLIC_COLUMNS = frozenset(
    {
        "mmsi",
        "source_vessel_id",
        "source_id",
        "vessel_name",
        "imo",
        "call_sign",
    }
)


@dataclass(frozen=True)
class FeatureConfig:
    segment_gap_seconds: float
    window_duration_seconds: float
    window_stride_seconds: float
    minimum_window_observations: int
    minimum_observed_span_seconds: float
    minimum_valid_fraction: float
    low_speed_threshold_knots: float
    course_min_speed_knots: float
    minimum_displacement_for_ratio_m: float

    def __post_init__(self) -> None:
        positive = (
            "segment_gap_seconds",
            "window_duration_seconds",
            "window_stride_seconds",
            "minimum_observed_span_seconds",
        )
        for name in positive:
            value = getattr(self, name)
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise ValueError(f"{name} must be numeric")
            if not math.isfinite(float(value)) or float(value) <= 0:
                raise ValueError(f"{name} must be positive and finite")
        if (
            not isinstance(self.minimum_window_observations, int)
            or isinstance(self.minimum_window_observations, bool)
            or self.minimum_window_observations <= 0
        ):
            raise ValueError("minimum_window_observations must be a positive integer")
        if self.window_stride_seconds > self.window_duration_seconds:
            raise ValueError(
                "window_stride_seconds must not exceed window_duration_seconds"
            )
        if not 0.0 <= self.minimum_valid_fraction <= 1.0:
            raise ValueError("minimum_valid_fraction must be between 0 and 1")
        for name in (
            "low_speed_threshold_knots",
            "course_min_speed_knots",
            "minimum_displacement_for_ratio_m",
        ):
            value = getattr(self, name)
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise ValueError(f"{name} must be numeric")
            if not math.isfinite(float(value)) or float(value) < 0:
                raise ValueError(f"{name} must be non-negative and finite")


@dataclass(frozen=True)
class ValidationStats:
    input_rows: int
    input_out_of_order_pairs: int
    invalid_sog_rows: int
    invalid_cog_rows: int
    invalid_heading_rows: int


@dataclass(frozen=True)
class ValidatedObservations:
    frame: pd.DataFrame
    stats: ValidationStats


def load_feature_config(path: Path) -> FeatureConfig:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("feature configuration must be a JSON object")
    expected = {field.name for field in fields(FeatureConfig)}
    actual = set(payload)
    unexpected = sorted(actual - expected)
    missing = sorted(expected - actual)
    if unexpected:
        raise ValueError(f"unknown feature configuration keys: {', '.join(unexpected)}")
    if missing:
        raise ValueError(f"missing feature configuration keys: {', '.join(missing)}")
    return FeatureConfig(**payload)


def assert_public_feature_schema(columns: Iterable[str]) -> None:
    normalized = {str(column).casefold() for column in columns}
    exposed = sorted(normalized.intersection(FORBIDDEN_PUBLIC_COLUMNS))
    if exposed:
        raise ValueError(f"public feature schema contains forbidden identifiers: {exposed}")


def validate_observations(frame: pd.DataFrame) -> ValidatedObservations:
    assert_public_feature_schema(frame.columns)
    missing = sorted(set(PHASE1_COLUMNS).difference(frame.columns))
    unexpected = sorted(set(frame.columns).difference(PHASE1_COLUMNS))
    if missing:
        raise ValueError(f"missing Phase 1 observation columns: {', '.join(missing)}")
    if unexpected:
        raise ValueError(f"unexpected Phase 1 observation columns: {', '.join(unexpected)}")

    working = frame.loc[:, PHASE1_COLUMNS].copy()
    working["track_id"] = working["track_id"].astype("string").str.strip()
    invalid_track = working["track_id"].isna() | working["track_id"].eq("")
    if invalid_track.any():
        raise ValueError(f"track_id is missing or empty in {int(invalid_track.sum())} rows")

    working["base_date_time"] = pd.to_datetime(
        working["base_date_time"], errors="coerce", utc=True, format="mixed"
    )
    invalid_time = working["base_date_time"].isna()
    if invalid_time.any():
        raise ValueError(
            f"base_date_time is missing or invalid in {int(invalid_time.sum())} rows"
        )

    longitude = pd.to_numeric(working["longitude"], errors="coerce")
    latitude = pd.to_numeric(working["latitude"], errors="coerce")
    valid_coordinates = (
        np.isfinite(longitude)
        & np.isfinite(latitude)
        & longitude.between(-180.0, 180.0, inclusive="both")
        & latitude.between(-90.0, 90.0, inclusive="both")
    ).fillna(False)
    if not valid_coordinates.all():
        raise ValueError(
            f"coordinates are missing, non-finite, or out of range in "
            f"{int((~valid_coordinates).sum())} rows"
        )
    working["longitude"] = longitude.astype(float)
    working["latitude"] = latitude.astype(float)

    input_gaps = working.groupby("track_id", sort=False)["base_date_time"].diff()
    input_out_of_order_pairs = int(
        input_gaps.dt.total_seconds().lt(0).sum()
    )

    invalid_counts: dict[str, int] = {}
    navigation_rules = {
        "sog": lambda values: values.ge(0),
        "cog": lambda values: values.ge(0) & values.lt(360),
        "heading": lambda values: values.ge(0) & values.le(359),
    }
    for name, rule in navigation_rules.items():
        original = working[name]
        numeric = pd.to_numeric(original, errors="coerce")
        valid = numeric.notna() & np.isfinite(numeric) & rule(numeric)
        invalid = original.notna() & ~valid
        invalid_counts[name] = int(invalid.sum())
        working[name] = numeric.where(valid, np.nan).astype(float)

    working["_source_row_order"] = np.arange(len(working))
    working = working.sort_values(
        ["track_id", "base_date_time", "_source_row_order"], kind="mergesort"
    )
    working = working.drop(columns="_source_row_order").reset_index(drop=True)
    return ValidatedObservations(
        frame=working,
        stats=ValidationStats(
            input_rows=len(working),
            input_out_of_order_pairs=input_out_of_order_pairs,
            invalid_sog_rows=invalid_counts["sog"],
            invalid_cog_rows=invalid_counts["cog"],
            invalid_heading_rows=invalid_counts["heading"],
        ),
    )
