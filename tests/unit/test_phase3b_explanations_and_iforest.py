from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from apps.api.seawatch.review_ranking.config import load_phase3b_config
from apps.api.seawatch.review_ranking.contracts import FeatureReference, ReferenceProfile, TransformedFeatures
from apps.api.seawatch.review_ranking.explanations import build_evidence_reasons
from apps.api.seawatch.review_ranking.isolation_forest import fit_isolation_forest, score_isolation_forest
from apps.api.seawatch.review_ranking.ranking import rank_method_scores
from apps.api.seawatch.review_ranking.pipeline import _rank_all
from apps.api.seawatch.review_ranking.statistics import score_percentile_baseline


def _features(rows: int = 30) -> TransformedFeatures:
    names = ("sog_median_knots", "sog_p95_knots", "low_speed_fraction", "low_speed_duration_seconds", "path_distance_m", "displacement_m")
    raw = pd.DataFrame({name: np.linspace(i, i + 10, rows) for i, name in enumerate(names)})
    pct = raw.rank(pct=True)
    return TransformedFeatures(names, raw, raw.copy(), (raw - raw.median()) / 2, pct, pd.DataFrame(False, index=raw.index, columns=names))


def test_percentile_explanations_are_feature_derived_and_neutral() -> None:
    config = load_phase3b_config(Path("config/phase3b_review_ranking_v1.json"))
    features = _features()
    scores = score_percentile_baseline(features, config)
    reasons = build_evidence_reasons(scores.method_id, scores.components, features, config)
    assert all(1 <= len(reason_set) <= 3 for reason_set in reasons)
    text = " ".join(reason.message for reason_set in reasons for reason in reason_set).lower()
    assert "january 1 background" in text
    for word in ("probability", "confidence", "hostile", "illegal", "dangerous", "suspicious", "malicious"):
        assert word not in text
    assert {r.attribution_kind for rs in reasons for r in rs} == {"exact_component"}


def test_isolation_forest_is_deterministic_and_rejects_feature_mismatch() -> None:
    config = load_phase3b_config(Path("config/phase3b_review_ranking_v1.json"))
    features = _features(80)
    one = fit_isolation_forest(features, config)
    two = fit_isolation_forest(features, config)
    assert one.parameter_hash == two.parameter_hash
    assert score_isolation_forest(one, features, config).scores.equals(score_isolation_forest(two, features, config).scores)
    assert not hasattr(score_isolation_forest(one, features, config), "labels")
    bad = TransformedFeatures(tuple(reversed(features.feature_names)), features.raw, features.clipped, features.robust_scaled, features.percentiles, features.missing)
    with pytest.raises(ValueError, match="feature order"):
        score_isolation_forest(one, bad, config)
    scored = score_isolation_forest(one, features, config)
    reasons = build_evidence_reasons(scored.method_id, scored.components, features, config)
    assert all("not model attribution" in reason.message.lower() for group in reasons for reason in group)


def test_ranking_ties_are_stable_and_shortlist_exact_budget() -> None:
    config = load_phase3b_config(Path("config/phase3b_review_ranking_v1.json"))
    features = _features(25)
    score = score_percentile_baseline(features, config)
    score = type(score).validate(score.method_id, pd.Series(50.0, index=features.raw.index), score.components)
    metadata = pd.DataFrame({
        "window_start_utc": pd.date_range("2024-01-02", periods=25, freq="min", tz="UTC")[::-1],
        "track_id": [f"t{i%5}" for i in range(25)],
        "window_id": [f"w{i:02}" for i in range(25)],
    })
    ranked = rank_method_scores(metadata, score, review_budget=20, calibration_cutoff=50)
    assert ranked["shortlisted"].sum() == 20
    assert ranked["window_start_utc"].is_monotonic_increasing
    assert ranked["review_status"].eq("unreviewed").all()


def test_ranked_explanation_stays_with_its_source_window() -> None:
    from datetime import date
    from apps.api.seawatch.review_ranking.contracts import SplitWindows

    config = load_phase3b_config(Path("config/phase3b_review_ranking_v1.json"))
    features = _features(3)
    score = score_percentile_baseline(features, config)
    frame = pd.DataFrame({
        "track_id": ["a", "b", "c"], "segment_id": ["sa", "sb", "sc"], "window_id": ["wa", "wb", "wc"],
        "window_start_utc": pd.date_range("2024-01-02", periods=3, freq="min", tz="UTC"),
        "window_end_utc": pd.date_range("2024-01-02 00:30", periods=3, freq="min", tz="UTC"),
    })
    split = SplitWindows(date(2024, 1, 2), "calibration", Path("x"), "hash", frame, 0)
    ranks, _ = _rank_all(split, features, {score.method_id: score}, config)
    ranked = ranks[score.method_id]
    assert ranked["schema_version"].eq("phase3b-review-ranking-v1").all()
    assert ranked["method_version"].eq("phase3b-v1").all()
    assert ranked["allowed_review_actions"].eq("review,relevant,false_positive,keep_monitoring").all()
    for _, row in ranked.iterrows():
        source = frame.index[frame["window_id"].eq(row["window_id"])][0]
        reasons = __import__("json").loads(row["evidence_reasons"])
        assert reasons[0]["observed_value"] == features.raw.loc[source, reasons[0]["feature_name"]]
