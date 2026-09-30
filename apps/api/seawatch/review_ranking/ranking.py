"""Shared deterministic ranking contract."""

from __future__ import annotations

import pandas as pd

from .contracts import ScoreFrame


def rank_method_scores(metadata: pd.DataFrame, scores: ScoreFrame, *, review_budget: int, calibration_cutoff: float | None) -> pd.DataFrame:
    required = ["window_start_utc", "track_id", "window_id"]
    if review_budget <= 0 or any(name not in metadata for name in required):
        raise ValueError("valid review budget and ranking metadata are required")
    result = metadata.copy()
    result["method_id"] = scores.method_id
    result["review_priority_score"] = scores.scores.to_numpy()
    result = result.sort_values(["review_priority_score", "window_start_utc", "track_id", "window_id"], ascending=[False, True, True, True], kind="mergesort").reset_index(drop=True)
    result["rank_within_date_method"] = range(1, len(result) + 1)
    result["shortlisted"] = result["rank_within_date_method"].le(min(review_budget, len(result)))
    result["calibration_cutoff_exceeded"] = False if calibration_cutoff is None else result["review_priority_score"].ge(calibration_cutoff)
    result["review_status"] = "unreviewed"
    return result
