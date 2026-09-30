"""Interpretable movement features for deterministic trajectory windows."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from .contracts import FeatureConfig, assert_public_feature_schema
from .geodesy import circular_difference_degrees, path_metrics
from .windowing import WINDOW_METADATA_COLUMNS


FEATURE_COLUMNS = (
    "sog_median_knots",
    "sog_p95_knots",
    "low_speed_fraction",
    "low_speed_duration_seconds",
    "path_distance_m",
    "displacement_m",
    "path_displacement_ratio",
    "course_change_abs_sum_deg",
    "course_change_abs_p95_deg",
    "heading_cog_abs_median_deg",
)

FEATURE_UNITS = {
    "sog_median_knots": "knots",
    "sog_p95_knots": "knots",
    "low_speed_fraction": "fraction",
    "low_speed_duration_seconds": "seconds",
    "path_distance_m": "metres",
    "displacement_m": "metres",
    "path_displacement_ratio": "unitless",
    "course_change_abs_sum_deg": "degrees",
    "course_change_abs_p95_deg": "degrees",
    "heading_cog_abs_median_deg": "degrees",
}


def _empty_features() -> dict[str, float]:
    return {name: math.nan for name in FEATURE_COLUMNS}


def _compute_features(
    members: pd.DataFrame, metadata: pd.Series, config: FeatureConfig
) -> dict[str, float | None]:
    if metadata["window_quality_status"] != "sufficient":
        return _empty_features()

    features: dict[str, float | None] = _empty_features()
    timestamps = members["base_date_time"]
    interval_seconds = timestamps.diff().dt.total_seconds()

    if (
        int(metadata["sog_valid_count"]) > 0
        and float(metadata["sog_valid_fraction"]) >= config.minimum_valid_fraction
    ):
        valid_sog = members["sog"].dropna().astype(float)
        features["sog_median_knots"] = float(valid_sog.median())
        features["sog_p95_knots"] = float(valid_sog.quantile(0.95))
        low_speed = members["sog"].notna() & members["sog"].lt(
            config.low_speed_threshold_knots
        )
        features["low_speed_fraction"] = float(low_speed.sum() / len(valid_sog))
        low_speed_intervals = (
            low_speed
            & low_speed.shift(fill_value=False)
            & interval_seconds.gt(0)
        )
        features["low_speed_duration_seconds"] = float(
            interval_seconds.where(low_speed_intervals, 0.0).sum()
        )

    path = path_metrics(
        members["longitude"],
        members["latitude"],
        minimum_displacement_m=config.minimum_displacement_for_ratio_m,
    )
    features["path_distance_m"] = path.path_distance_m
    features["displacement_m"] = path.displacement_m
    features["path_displacement_ratio"] = path.path_displacement_ratio

    cog_valid = members["cog"].notna()
    sog_course_valid = members["sog"].ge(config.course_min_speed_knots)
    eligible_course = (
        cog_valid
        & cog_valid.shift(fill_value=False)
        & sog_course_valid
        & sog_course_valid.shift(fill_value=False)
        & interval_seconds.gt(0)
    )
    if (
        float(metadata["cog_valid_fraction"]) >= config.minimum_valid_fraction
        and int(eligible_course.sum()) >= 2
    ):
        changes = pd.Series(
            [
                abs(circular_difference_degrees(members["cog"].iloc[index - 1], value))
                for index, value in enumerate(members["cog"])
                if index > 0 and bool(eligible_course.iloc[index])
            ],
            dtype=float,
        )
        features["course_change_abs_sum_deg"] = float(changes.sum())
        features["course_change_abs_p95_deg"] = float(changes.quantile(0.95))

    paired_heading = (
        members["heading"].notna()
        & members["cog"].notna()
        & members["sog"].ge(config.course_min_speed_knots)
    )
    if (
        float(metadata["heading_cog_paired_fraction"])
        >= config.minimum_valid_fraction
        and paired_heading.any()
    ):
        differences = [
            abs(circular_difference_degrees(heading, cog))
            for heading, cog in zip(
                members.loc[paired_heading, "heading"],
                members.loc[paired_heading, "cog"],
                strict=True,
            )
        ]
        features["heading_cog_abs_median_deg"] = float(np.median(differences))
    return features


def compute_window_features(
    observations: pd.DataFrame,
    windows: pd.DataFrame,
    config: FeatureConfig,
) -> pd.DataFrame:
    """Compute ten neutral movement features and remove private membership."""

    required = {*WINDOW_METADATA_COLUMNS, "_observation_positions"}
    missing = sorted(required.difference(windows.columns))
    if missing:
        raise ValueError(f"missing window columns: {', '.join(missing)}")
    rows: list[dict[str, object]] = []
    for _, window in windows.iterrows():
        positions = tuple(int(value) for value in window["_observation_positions"])
        members = observations.iloc[list(positions)]
        row = {name: window[name] for name in WINDOW_METADATA_COLUMNS}
        row.update(_compute_features(members, window, config))
        rows.append(row)
    result = pd.DataFrame(rows, columns=(*WINDOW_METADATA_COLUMNS, *FEATURE_COLUMNS))
    assert_public_feature_schema(result.columns)
    return result
