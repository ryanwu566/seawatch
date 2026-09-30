"""Track metadata service.

Reads the existing Phase 3B ranking artifacts and projects them to privacy-safe
trajectory metadata. No ranking is recomputed here.
"""

from __future__ import annotations

import pandas as pd

from ..schemas.track import TrackMetadata
from .artifacts import load_ranking_frame


def _coalesce_float(value: object, default: float = 0.0) -> float:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _coalesce_int(value: object, default: int = 0) -> int:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def list_tracks(*, use_cache: bool = True) -> list[TrackMetadata]:
    """Return distinct privacy-safe trajectory metadata records.

    One record per (track_id, source_date, window_id) is derived from the ranking
    outputs. Duration is the observed window duration in seconds.

    Raises:
        MissingArtifactError: If no Phase 3B ranking artifact exists.
    """

    frame = load_ranking_frame(use_cache=use_cache)

    columns = ["track_id", "source_date", "window_id", "observed_duration_seconds", "observation_count"]
    present = [name for name in columns if name in frame.columns]
    subset = frame[present].copy()

    # Collapse to unique trajectory-window rows; the ranking frame repeats a row
    # per ranking method.
    dedupe_keys = [name for name in ("track_id", "source_date", "window_id") if name in subset.columns]
    if dedupe_keys:
        subset = subset.drop_duplicates(subset=dedupe_keys)

    sort_keys = [name for name in ("source_date", "track_id", "window_id") if name in subset.columns]
    if sort_keys:
        subset = subset.sort_values(sort_keys, kind="mergesort")

    tracks: list[TrackMetadata] = []
    for row in subset.to_dict(orient="records"):
        tracks.append(
            TrackMetadata(
                track_id=str(row.get("track_id", "")),
                date=str(row.get("source_date", "")),
                duration=_coalesce_float(row.get("observed_duration_seconds")),
                observation_count=_coalesce_int(row.get("observation_count")),
            )
        )
    return tracks
