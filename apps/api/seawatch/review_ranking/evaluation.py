"""Track-aware calibration helpers without labels."""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np
import pandas as pd

from .contracts import BootstrapTrackDraw


def compare_rankings(reference: pd.DataFrame, candidate: pd.DataFrame, *, budgets: tuple[int, ...]) -> dict[str, float | None]:
    """Compare two deterministic rankings without interpreting either as labels."""

    required = {"window_id", "review_priority_score"}
    if not required.issubset(reference) or not required.issubset(candidate):
        raise ValueError("ranking comparison requires window IDs and scores")
    result: dict[str, float | None] = {}
    for budget in budgets:
        left = set(reference.head(budget)["window_id"].astype(str))
        right = set(candidate.head(budget)["window_id"].astype(str))
        union = left | right
        result[f"top{budget}_jaccard"] = len(left & right) / len(union) if union else None
    left = reference[["window_id", "review_priority_score"]].copy()
    right = candidate[["window_id", "review_priority_score"]].copy()
    left["reference_rank"] = np.arange(1, len(left) + 1)
    right["candidate_rank"] = np.arange(1, len(right) + 1)
    merged = left.merge(right, on="window_id", suffixes=("_reference", "_candidate"), validate="one_to_one")
    result["spearman_rank_correlation"] = float(merged["reference_rank"].corr(merged["candidate_rank"], method="spearman")) if len(merged) > 1 else None
    result["mean_absolute_score_change"] = float((merged["review_priority_score_reference"] - merged["review_priority_score_candidate"]).abs().mean()) if len(merged) else None
    return result


def cluster_bootstrap_track_draws(track_ids: pd.Series, *, replicates: int, seed: int) -> tuple[tuple[BootstrapTrackDraw, ...], ...]:
    if replicates <= 0:
        raise ValueError("replicates must be positive")
    tracks = tuple(sorted(str(value) for value in track_ids.drop_duplicates()))
    if not tracks:
        return tuple()
    rows = {track: tuple(int(index) for index in track_ids.index[track_ids.astype(str).eq(track)]) for track in tracks}
    rng = np.random.default_rng(seed)
    result = []
    for replicate in range(replicates):
        sampled = rng.choice(tracks, size=len(tracks), replace=True)
        result.append(tuple(BootstrapTrackDraw(str(track), f"r{replicate:03}:d{draw:03}", rows[str(track)]) for draw, track in enumerate(sampled)))
    return tuple(result)


def select_demo_method(metrics: Mapping[str, Mapping[str, object]], *, tie_tolerance: float) -> str:
    eligible = {name: float(values["median_top20_jaccard"]) for name, values in metrics.items() if values.get("eligible") is True}
    if not eligible:
        raise ValueError("no eligible review-ranking method")
    best = max(eligible.values())
    contenders = {name for name, value in eligible.items() if best - value < tie_tolerance}
    for name in ("empirical_percentile", "rule", "robust_mad", "isolation_forest"):
        if name in contenders:
            return name
    return max(eligible, key=eligible.get)
