from __future__ import annotations

import pandas as pd
import pytest

from apps.api.seawatch.review_ranking.evaluation import (
    cluster_bootstrap_track_draws,
    compare_rankings,
    select_demo_method,
)


def test_track_bootstrap_preserves_whole_tracks_and_relabels_draws() -> None:
    ids = pd.Series(["a", "a", "b", "c", "c", "c"])
    draws = cluster_bootstrap_track_draws(ids, replicates=5, seed=42)
    assert draws == cluster_bootstrap_track_draws(ids, replicates=5, seed=42)
    assert len(draws) == 5
    for replicate in draws:
        for draw in replicate:
            expected = tuple(ids.index[ids.eq(draw.source_track_id)])
            assert draw.row_indices == expected
        assert len({draw.draw_instance_id for draw in replicate}) == len(replicate)


def test_method_selection_prefers_percentile_within_stability_tie() -> None:
    metrics = {
        "rule": {"eligible": True, "median_top20_jaccard": 0.71},
        "empirical_percentile": {"eligible": True, "median_top20_jaccard": 0.68},
        "robust_mad": {"eligible": True, "median_top20_jaccard": 0.70},
        "isolation_forest": {"eligible": True, "median_top20_jaccard": 0.72},
    }
    assert select_demo_method(metrics, tie_tolerance=0.05) == "empirical_percentile"
    with pytest.raises(ValueError, match="eligible"):
        select_demo_method({"rule": {"eligible": False, "median_top20_jaccard": 1.0}}, tie_tolerance=0.05)


def test_ranking_comparison_reports_workload_overlap_and_rank_shift() -> None:
    reference = pd.DataFrame({"window_id": ["a", "b", "c"], "review_priority_score": [3.0, 2.0, 1.0]})
    candidate = pd.DataFrame({"window_id": ["a", "c", "b"], "review_priority_score": [3.0, 2.0, 1.0]})
    metrics = compare_rankings(reference, candidate, budgets=(1, 2, 3))
    assert metrics["top1_jaccard"] == 1.0
    assert metrics["top2_jaccard"] == 1 / 3
    assert metrics["top3_jaccard"] == 1.0
    assert metrics["spearman_rank_correlation"] == 0.5
    assert metrics["mean_absolute_score_change"] == 2 / 3
