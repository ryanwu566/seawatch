"""Deterministic time-gap segmentation for validated observations."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .contracts import FeatureConfig, PHASE1_COLUMNS


SEGMENT_SUMMARY_COLUMNS = (
    "track_id",
    "segment_id",
    "segment_ordinal",
    "segment_start_utc",
    "segment_end_utc",
    "segment_duration_seconds",
    "observation_count",
    "median_gap_seconds",
    "max_gap_seconds",
    "zero_duration_interval_count",
    "sog_valid_count",
    "sog_valid_fraction",
    "cog_valid_count",
    "cog_valid_fraction",
    "heading_valid_count",
    "heading_valid_fraction",
    "vessel_type",
    "vessel_type_consistent",
    "segment_quality_status",
)


@dataclass(frozen=True)
class SegmentationResult:
    observations: pd.DataFrame
    segments: pd.DataFrame


def _consistent_vessel_type(values: pd.Series) -> tuple[object, bool]:
    unique = pd.unique(values.dropna())
    if len(unique) == 1:
        return unique[0], True
    return np.nan, False


def _segment_summary(segment: pd.DataFrame, config: FeatureConfig) -> dict[str, object]:
    timestamps = segment["base_date_time"]
    gaps = timestamps.diff().dt.total_seconds().dropna()
    positive = gaps[gaps > 0]
    count = len(segment)
    duration = float((timestamps.iloc[-1] - timestamps.iloc[0]).total_seconds())
    if count < 2:
        quality = "insufficient_observations"
    elif duration < config.window_duration_seconds:
        quality = "insufficient_duration"
    else:
        quality = "sufficient"
    vessel_type, vessel_type_consistent = _consistent_vessel_type(
        segment["vessel_type"]
    )
    result: dict[str, object] = {
        "track_id": str(segment["track_id"].iloc[0]),
        "segment_id": str(segment["segment_id"].iloc[0]),
        "segment_ordinal": int(segment["segment_ordinal"].iloc[0]),
        "segment_start_utc": timestamps.iloc[0],
        "segment_end_utc": timestamps.iloc[-1],
        "segment_duration_seconds": duration,
        "observation_count": count,
        "median_gap_seconds": float(positive.median()) if len(positive) else np.nan,
        "max_gap_seconds": float(positive.max()) if len(positive) else np.nan,
        "zero_duration_interval_count": int((gaps == 0).sum()),
        "vessel_type": vessel_type,
        "vessel_type_consistent": vessel_type_consistent,
        "segment_quality_status": quality,
    }
    for field in ("sog", "cog", "heading"):
        valid_count = int(segment[field].notna().sum())
        result[f"{field}_valid_count"] = valid_count
        result[f"{field}_valid_fraction"] = valid_count / count if count else 0.0
    return result


def segment_observations(
    frame: pd.DataFrame, config: FeatureConfig
) -> SegmentationResult:
    """Split each validated track when its preceding UTC gap exceeds the limit."""

    missing = sorted(set(PHASE1_COLUMNS).difference(frame.columns))
    if missing:
        raise ValueError(f"missing validated observation columns: {', '.join(missing)}")
    working = frame.loc[:, PHASE1_COLUMNS].copy().reset_index(drop=True)
    gaps = working.groupby("track_id", sort=False)["base_date_time"].diff()
    gap_seconds = gaps.dt.total_seconds()
    if (gap_seconds.dropna() < 0).any():
        raise RuntimeError("negative time gap encountered after validation and sorting")

    split = gap_seconds.gt(config.segment_gap_seconds).fillna(False)
    ordinals = split.groupby(working["track_id"], sort=False).cumsum().astype(int) + 1
    working["segment_ordinal"] = ordinals
    working["segment_id"] = [
        f"{track_id}:s{ordinal:04d}"
        for track_id, ordinal in zip(
            working["track_id"], working["segment_ordinal"], strict=True
        )
    ]
    working["preceding_gap_seconds"] = gap_seconds.astype(float)
    observation_columns = [
        *PHASE1_COLUMNS,
        "segment_id",
        "segment_ordinal",
        "preceding_gap_seconds",
    ]
    working = working.loc[:, observation_columns]

    summaries = [
        _segment_summary(segment, config)
        for _, segment in working.groupby("segment_id", sort=False)
    ]
    segments = pd.DataFrame(summaries, columns=SEGMENT_SUMMARY_COLUMNS)
    return SegmentationResult(observations=working, segments=segments)
