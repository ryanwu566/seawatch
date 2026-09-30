"""Deterministic full-duration windows within trajectory segments."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .contracts import FeatureConfig


WINDOW_METADATA_COLUMNS = (
    "track_id",
    "segment_id",
    "window_id",
    "window_ordinal",
    "window_start_utc",
    "window_end_utc",
    "first_observation_utc",
    "last_observation_utc",
    "observation_count",
    "observed_duration_seconds",
    "median_gap_seconds",
    "max_gap_seconds",
    "zero_duration_interval_count",
    "sog_valid_count",
    "sog_valid_fraction",
    "cog_valid_count",
    "cog_valid_fraction",
    "heading_cog_paired_count",
    "heading_cog_paired_fraction",
    "eligible_course_pair_count",
    "vessel_type",
    "vessel_type_consistent",
    "window_quality_status",
)


def _consistent_vessel_type(values: pd.Series) -> tuple[object, bool]:
    unique = pd.unique(values.dropna())
    if len(unique) == 1:
        return unique[0], True
    return np.nan, False


def _window_row(
    members: pd.DataFrame,
    positions: tuple[int, ...],
    *,
    track_id: str,
    segment_id: str,
    ordinal: int,
    window_start: pd.Timestamp,
    window_end: pd.Timestamp,
    config: FeatureConfig,
) -> dict[str, object]:
    timestamps = members["base_date_time"]
    gaps = timestamps.diff().dt.total_seconds().dropna()
    positive = gaps[gaps > 0]
    count = len(members)
    observed_duration = float(
        (timestamps.iloc[-1] - timestamps.iloc[0]).total_seconds()
    )
    if count < config.minimum_window_observations:
        quality = "insufficient_observations"
    elif observed_duration < config.minimum_observed_span_seconds:
        quality = "insufficient_span"
    else:
        quality = "sufficient"

    sog_valid = members["sog"].notna()
    cog_valid = members["cog"].notna()
    heading_cog_paired = (
        members["heading"].notna()
        & cog_valid
        & members["sog"].ge(config.course_min_speed_knots)
    )
    positive_interval = timestamps.diff().dt.total_seconds().gt(0)
    eligible_course_pair = (
        cog_valid
        & cog_valid.shift(fill_value=False)
        & members["sog"].ge(config.course_min_speed_knots)
        & members["sog"].shift().ge(config.course_min_speed_knots)
        & positive_interval
    )
    vessel_type, vessel_type_consistent = _consistent_vessel_type(
        members["vessel_type"]
    )
    return {
        "track_id": track_id,
        "segment_id": segment_id,
        "window_id": f"{segment_id}:w{ordinal:04d}",
        "window_ordinal": ordinal,
        "window_start_utc": window_start,
        "window_end_utc": window_end,
        "first_observation_utc": timestamps.iloc[0],
        "last_observation_utc": timestamps.iloc[-1],
        "observation_count": count,
        "observed_duration_seconds": observed_duration,
        "median_gap_seconds": float(positive.median()) if len(positive) else np.nan,
        "max_gap_seconds": float(positive.max()) if len(positive) else np.nan,
        "zero_duration_interval_count": int((gaps == 0).sum()),
        "sog_valid_count": int(sog_valid.sum()),
        "sog_valid_fraction": float(sog_valid.mean()),
        "cog_valid_count": int(cog_valid.sum()),
        "cog_valid_fraction": float(cog_valid.mean()),
        "heading_cog_paired_count": int(heading_cog_paired.sum()),
        "heading_cog_paired_fraction": float(heading_cog_paired.mean()),
        "eligible_course_pair_count": int(eligible_course_pair.sum()),
        "vessel_type": vessel_type,
        "vessel_type_consistent": vessel_type_consistent,
        "window_quality_status": quality,
        "_observation_positions": positions,
    }


def build_feature_windows(
    observations: pd.DataFrame,
    segments: pd.DataFrame,
    config: FeatureConfig,
) -> pd.DataFrame:
    """Build half-open windows that never leave a track segment."""

    required_observations = {
        "track_id",
        "segment_id",
        "base_date_time",
        "sog",
        "cog",
        "heading",
        "vessel_type",
    }
    missing_observations = sorted(required_observations.difference(observations.columns))
    if missing_observations:
        raise ValueError(
            f"missing window observation columns: {', '.join(missing_observations)}"
        )
    required_segments = {
        "track_id",
        "segment_id",
        "segment_start_utc",
        "segment_end_utc",
    }
    missing_segments = sorted(required_segments.difference(segments.columns))
    if missing_segments:
        raise ValueError(
            f"missing segment summary columns: {', '.join(missing_segments)}"
        )

    working = observations.reset_index(drop=True)
    duration = pd.Timedelta(seconds=config.window_duration_seconds)
    stride = pd.Timedelta(seconds=config.window_stride_seconds)
    rows: list[dict[str, object]] = []
    for segment in segments.itertuples(index=False):
        track_id = str(segment.track_id)
        segment_id = str(segment.segment_id)
        segment_start = pd.Timestamp(segment.segment_start_utc)
        segment_end = pd.Timestamp(segment.segment_end_utc)
        segment_mask = working["segment_id"].astype(str).eq(segment_id) & working[
            "track_id"
        ].astype(str).eq(track_id)
        window_start = segment_start
        ordinal = 1
        while window_start + duration <= segment_end:
            window_end = window_start + duration
            member_mask = (
                segment_mask
                & working["base_date_time"].ge(window_start)
                & working["base_date_time"].lt(window_end)
            )
            positions = tuple(int(value) for value in np.flatnonzero(member_mask))
            if positions:
                members = working.iloc[list(positions)]
                rows.append(
                    _window_row(
                        members,
                        positions,
                        track_id=track_id,
                        segment_id=segment_id,
                        ordinal=ordinal,
                        window_start=window_start,
                        window_end=window_end,
                        config=config,
                    )
                )
            ordinal += 1
            window_start += stride
    return pd.DataFrame(rows, columns=(*WINDOW_METADATA_COLUMNS, "_observation_positions"))
