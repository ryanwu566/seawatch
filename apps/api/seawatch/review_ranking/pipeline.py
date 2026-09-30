"""Staged Phase 3B orchestration with an explicit held-out access gate."""

from __future__ import annotations

from dataclasses import asdict, replace
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .config import Phase3BConfig, load_phase3b_config, phase3b_config_sha256
from .contracts import FeaturePolicyAnalysis, ScoreFrame, SplitWindows, TransformedFeatures
from .data import load_split_windows
from .evaluation import cluster_bootstrap_track_draws, compare_rankings
from .explanations import build_evidence_reasons
from .feature_policy import analyze_feature_policy, feature_policy_payload
from .io import write_json_atomic, write_rankings
from .isolation_forest import fit_isolation_forest, score_isolation_forest
from .ranking import rank_method_scores
from .reference import fit_reference_profile, transform_with_reference
from .rules import score_rule_baseline
from .statistics import score_percentile_baseline, score_robust_mad_baseline


CONFIG = Path("config/phase3b_review_ranking_v1.json")
COHORT = Path("data/manifests/noaa_ais_2024-01-01_to_2024-01-03_sf_bay_phase3a.json")
POLICY = Path("docs/qa/phase3b-feature-selection.json")
PROTOCOL = Path("docs/qa/phase3b-calibration.json")
EVALUATION = Path("docs/qa/phase3b-evaluation.json")
REPORT = Path("docs/phase3b-baseline-comparison-report.md")
LOCAL = Path("data/processed/review_ranking")


def _rooted(root: Path, path: Path | None, default: Path) -> Path:
    value = path or default
    return value if value.is_absolute() else root / value


def _hash_payload(payload: dict[str, object]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _load_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _score_methods(train_features: TransformedFeatures, later_features: TransformedFeatures, profile, config: Phase3BConfig) -> dict[str, ScoreFrame]:
    model = fit_isolation_forest(train_features, config)
    return {
        "rule": score_rule_baseline(later_features, profile, config),
        "empirical_percentile": score_percentile_baseline(later_features, config),
        "robust_mad": score_robust_mad_baseline(later_features, config),
        "isolation_forest": score_isolation_forest(model, later_features, config),
    }


def _rank_all(split: SplitWindows, features: TransformedFeatures, scores: dict[str, ScoreFrame], config: Phase3BConfig, cutoffs: dict[str, float] | None = None) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    metadata_names = [name for name in (
        "track_id", "segment_id", "window_id", "window_start_utc", "window_end_utc", "first_observation_utc", "last_observation_utc",
        "observation_count", "observed_duration_seconds", "max_gap_seconds", "zero_duration_interval_count", "sog_valid_fraction", "cog_valid_fraction",
    ) if name in split.frame]
    metadata = split.frame[metadata_names].copy()
    metadata["_source_position"] = np.arange(len(metadata))
    metadata["schema_version"] = "phase3b-review-ranking-v1"
    metadata["method_version"] = "phase3b-v1"
    metadata["allowed_review_actions"] = "review,relevant,false_positive,keep_monitoring"
    metadata["source_date"] = split.source_date.isoformat()
    metadata["split_role"] = split.split_role
    ranks: dict[str, pd.DataFrame] = {}
    combined: list[pd.DataFrame] = []
    for method, score in scores.items():
        reasons = build_evidence_reasons(method, score.components, features, config)
        ranked = rank_method_scores(metadata, score, review_budget=config.calibration.review_budget, calibration_cutoff=None if cutoffs is None else cutoffs[method])
        ranked["evidence_reasons"] = [
            json.dumps([asdict(item) for item in reasons[int(position)]], sort_keys=True)
            for position in ranked["_source_position"]
        ]
        ranked = ranked.drop(columns="_source_position")
        ranks[method] = ranked
        combined.append(ranked)
    return ranks, pd.concat(combined, ignore_index=True)


def _bootstrap_stability(train: SplitWindows, calibration: SplitWindows, policy: FeaturePolicyAnalysis, baseline: dict[str, pd.DataFrame], config: Phase3BConfig) -> dict[str, dict[str, object]]:
    metric_names = tuple(f"top{budget}_jaccard" for budget in config.calibration.budgets) + ("spearman_rank_correlation", "mean_absolute_score_change")
    values = {name: {metric: [] for metric in metric_names} for name in baseline}
    draws = cluster_bootstrap_track_draws(train.frame["track_id"], replicates=config.calibration.bootstrap_replicates, seed=config.calibration.bootstrap_seed)

    def score_replicate(replicate):
        parts = []
        for draw in replicate:
            part = train.frame.loc[list(draw.row_indices)].copy()
            part["track_id"] = draw.draw_instance_id
            parts.append(part)
        sampled = pd.concat(parts, ignore_index=True)
        boot = SplitWindows(train.source_date, "train", train.artifact_path, train.artifact_sha256, sampled, train.rejected_count)
        try:
            profile = fit_reference_profile(boot, policy, config)
            train_features = transform_with_reference(sampled, profile)
            later_features = transform_with_reference(calibration.frame, profile)
            method_scores = _score_methods(train_features, later_features, profile, config)
            metadata = calibration.frame[["window_start_utc", "track_id", "window_id"]]
            ranked = {
                method: rank_method_scores(
                    metadata,
                    score,
                    review_budget=config.calibration.review_budget,
                    calibration_cutoff=None,
                )
                for method, score in method_scores.items()
            }
        except ValueError:
            return None
        return {
            method: compare_rankings(baseline[method], frame, budgets=config.calibration.budgets)
            for method, frame in ranked.items()
        }

    failures = 0
    with ThreadPoolExecutor(max_workers=min(4, len(draws))) as executor:
        results = executor.map(score_replicate, draws)
        for result in results:
            if result is None:
                failures += 1
                continue
            for method, metrics in result.items():
                for metric, score in metrics.items():
                    if score is not None:
                        values[method][metric].append(score)
    return {
        method: {
            "successful_replicates": len(scores["top20_jaccard"]),
            "failed_replicates": failures,
            **{f"median_{metric}": float(np.median(items)) if items else None for metric, items in scores.items()},
            "minimum_top20_jaccard": float(np.min(scores["top20_jaccard"])) if scores["top20_jaccard"] else None,
        }
        for method, scores in values.items()
    }


def _calibration_robustness(train: SplitWindows, calibration: SplitWindows, policy: FeaturePolicyAnalysis, baseline: dict[str, pd.DataFrame], config: Phase3BConfig) -> dict[str, object]:
    variants: dict[str, list[dict[str, object]]] = {name: [] for name in baseline}

    def record(variant_id: str, ranked: dict[str, pd.DataFrame], methods: tuple[str, ...]) -> None:
        for method in methods:
            variants[method].append({"variant_id": variant_id, **compare_rankings(baseline[method], ranked[method], budgets=config.calibration.budgets)})

    for low, high in ((0.005, 0.995), (0.02, 0.98)):
        variant_config = replace(config, reference=replace(config.reference, clip_low_quantile=low, clip_high_quantile=high))
        profile = fit_reference_profile(train, policy, variant_config)
        train_features = transform_with_reference(train.frame, profile)
        later_features = transform_with_reference(calibration.frame, profile)
        scores = _score_methods(train_features, later_features, profile, variant_config)
        ranked, _ = _rank_all(calibration, later_features, scores, variant_config)
        record(f"clip_{low:g}_{high:g}", ranked, tuple(baseline))

    base_profile = fit_reference_profile(train, policy, config)
    train_features = transform_with_reference(train.frame, base_profile)
    later_features = transform_with_reference(calibration.frame, base_profile)
    metadata = calibration.frame[["window_start_utc", "track_id", "window_id"]]
    for low, high in ((0.10, 0.90), (0.025, 0.975)):
        variant_config = replace(config, rules=replace(config.rules, low_quantile=low, high_quantile=high))
        score = score_rule_baseline(later_features, base_profile, variant_config)
        ranked = {"rule": rank_method_scores(metadata, score, review_budget=config.calibration.review_budget, calibration_cutoff=None)}
        record(f"rule_{low:g}_{high:g}", ranked, ("rule",))
    for seed, trees in ((7, 256), (101, 256), (42, 128), (42, 512)):
        variant_config = replace(config, isolation_forest=replace(config.isolation_forest, random_state=seed, n_estimators=trees))
        model = fit_isolation_forest(train_features, variant_config)
        score = score_isolation_forest(model, later_features, variant_config)
        ranked = {"isolation_forest": rank_method_scores(metadata, score, review_budget=config.calibration.review_budget, calibration_cutoff=None)}
        record(f"if_seed_{seed}_trees_{trees}", ranked, ("isolation_forest",))
    return {
        method: {
            "variants": items,
            "minimum_top20_jaccard": min(float(item["top20_jaccard"]) for item in items),
            "minimum_spearman_rank_correlation": min(float(item["spearman_rank_correlation"]) for item in items),
        }
        for method, items in variants.items()
    }


def select_features(*, root: Path, output: Path | None = None, overwrite: bool = False) -> Path:
    config_path, cohort_path = root / CONFIG, root / COHORT
    config = load_phase3b_config(config_path)
    splits = load_split_windows(cohort_path, ("train", "calibration"), root=root)
    policy = analyze_feature_policy(splits["train"], splits["calibration"], config)
    payload = feature_policy_payload(policy, input_hashes={name: split.artifact_sha256 for name, split in splits.items()}, config_sha256=phase3b_config_sha256(config_path))
    payload["split_roles_read"] = ["train", "calibration"]
    path = _rooted(root, output, POLICY)
    write_json_atomic(payload, path, overwrite=overwrite)
    return path


def calibrate(*, root: Path, output: Path | None = None, overwrite: bool = False) -> Path:
    config_path, cohort_path, policy_path = root / CONFIG, root / COHORT, root / POLICY
    config = load_phase3b_config(config_path)
    stored_policy = _load_json(policy_path)
    splits = load_split_windows(cohort_path, ("train", "calibration"), root=root)
    policy = analyze_feature_policy(splits["train"], splits["calibration"], config)
    if policy.policy_hash != stored_policy.get("policy_hash"):
        raise ValueError("feature policy hash mismatch")
    profile = fit_reference_profile(splits["train"], policy, config)
    train_features = transform_with_reference(splits["train"].frame, profile)
    calibration_features = transform_with_reference(splits["calibration"].frame, profile)
    scores = _score_methods(train_features, calibration_features, profile, config)
    ranks, combined = _rank_all(splits["calibration"], calibration_features, scores, config)
    stability = _bootstrap_stability(splits["train"], splits["calibration"], policy, ranks, config)
    robustness = _calibration_robustness(splits["train"], splits["calibration"], policy, ranks, config)
    metrics: dict[str, object] = {}
    cutoffs: dict[str, float] = {}
    for method, ranked in ranks.items():
        top = ranked[ranked["shortlisted"]]
        shares = top["track_id"].value_counts(normalize=True)
        cutoff = float(top["review_priority_score"].iloc[-1])
        cutoffs[method] = cutoff
        reason_coverage = float(top["evidence_reasons"].ne("[]").mean())
        stable = stability[method]["median_top20_jaccard"]
        eligible = bool(
            stable is not None and float(stable) >= config.calibration.minimum_jaccard
            and top["track_id"].nunique() >= config.calibration.minimum_tracks
            and float(shares.max()) <= config.calibration.maximum_track_share
            and reason_coverage == 1.0
        )
        metrics[method] = {
            **stability[method], "eligible": eligible, "calibration_cutoff": cutoff,
            "top20_distinct_tracks": int(top["track_id"].nunique()), "top20_maximum_track_share": float(shares.max()),
            "top20_reason_coverage": reason_coverage, "budget_scores": {str(k): float(ranked.iloc[min(k, len(ranked)) - 1]["review_priority_score"]) for k in config.calibration.budgets},
        }
    primary = config.primary_method
    payload: dict[str, object] = {
        "schema_version": "phase3b-calibration-v1", "selected_method": primary, "selection_basis": "approved primary demo candidate",
        "selected_method_eligible": bool(metrics[primary]["eligible"]), "method_metrics": metrics, "cutoffs": cutoffs,
        "robustness": robustness,
        "reference_hash": profile.reference_hash, "policy_hash": policy.policy_hash, "config_sha256": phase3b_config_sha256(config_path),
        "input_hashes": {name: split.artifact_sha256 for name, split in splits.items()}, "split_roles_read": ["train", "calibration"],
        "limitations": ["No anomaly labels or ground truth were used.", "Whole-track bootstrap respects clustered overlapping windows."],
    }
    payload["frozen_protocol_hash"] = _hash_payload(payload)
    path = _rooted(root, output, PROTOCOL)
    write_json_atomic(payload, path, overwrite=overwrite)
    local = root / LOCAL / "calibration_rankings.parquet"
    write_rankings(combined, local, {"protocol": str(payload["frozen_protocol_hash"])}, overwrite=overwrite)
    return path


def evaluate(*, root: Path, output: Path | None = None, overwrite: bool = False) -> Path:
    config_path, cohort_path = root / CONFIG, root / COHORT
    config = load_phase3b_config(config_path)
    stored_policy, protocol = _load_json(root / POLICY), _load_json(root / PROTOCOL)
    check = dict(protocol)
    frozen_hash = check.pop("frozen_protocol_hash", None)
    if frozen_hash != _hash_payload(check) or protocol.get("config_sha256") != phase3b_config_sha256(config_path):
        raise ValueError("frozen protocol/config hash mismatch")
    earlier = load_split_windows(cohort_path, ("train", "calibration"), root=root)
    policy = analyze_feature_policy(earlier["train"], earlier["calibration"], config)
    profile = fit_reference_profile(earlier["train"], policy, config)
    if policy.policy_hash != stored_policy.get("policy_hash") or profile.reference_hash != protocol.get("reference_hash"):
        raise ValueError("frozen feature/reference hash mismatch")
    held_out = load_split_windows(cohort_path, ("test",), root=root)["test"]
    train_features = transform_with_reference(earlier["train"].frame, profile)
    test_features = transform_with_reference(held_out.frame, profile)
    scores = _score_methods(train_features, test_features, profile, config)
    cutoffs = {str(name): float(value) for name, value in dict(protocol["cutoffs"]).items()}
    ranks, combined = _rank_all(held_out, test_features, scores, config, cutoffs)
    methods = {}
    for method, ranked in ranks.items():
        top = ranked[ranked["shortlisted"]]
        shares = top["track_id"].value_counts(normalize=True)
        methods[method] = {
            "exact_review_workload": len(top), "calibration_cutoff_exceedance_count": int(ranked["calibration_cutoff_exceeded"].sum()),
            "top20_distinct_tracks": int(top["track_id"].nunique()), "top20_maximum_track_share": float(shares.max()),
            "top20_reason_coverage": float(top["evidence_reasons"].ne("[]").mean()),
            "score_summary": {"minimum": float(ranked["review_priority_score"].min()), "median": float(ranked["review_priority_score"].median()), "maximum": float(ranked["review_priority_score"].max())},
        }
    payload: dict[str, object] = {
        "schema_version": "phase3b-evaluation-v1", "selected_method": protocol["selected_method"], "frozen_protocol_hash": frozen_hash,
        "methods": methods, "test_artifact_sha256": held_out.artifact_sha256, "split_roles_read_after_freeze": ["test"],
        "limitations": ["January 3 aggregate QA was visible during Phase 3A.", "No anomaly labels or ground truth exist.", "Windows and tracks are dependent."],
    }
    payload["evaluation_hash"] = _hash_payload(payload)
    path = _rooted(root, output, EVALUATION)
    write_json_atomic(payload, path, overwrite=overwrite)
    write_rankings(combined, root / LOCAL / "test_rankings.parquet", {"evaluation": str(payload["evaluation_hash"])}, overwrite=overwrite)
    return path


def report(*, root: Path, output: Path | None = None, overwrite: bool = False) -> Path:
    policy, protocol, evaluation = _load_json(root / POLICY), _load_json(root / PROTOCOL), _load_json(root / EVALUATION)
    lines = [
        "# Phase 3B Explainable Behavioral Review-Ranking Report", "", "SeaWatch prioritizes behavioral patterns for human review. Scores are not probabilities, confidence values, labels, or findings about intent or legality.", "",
        "## Frozen data roles", "", "- 2024-01-01: background/reference fit", "- 2024-01-02: calibration and method comparison", "- 2024-01-03: held-out temporal evaluation", "", "No random window split was used.", "",
        "## Feature policy", "", f"Active features: {', '.join(policy['active_features'])}.", f"Disabled conditional features: {', '.join(sorted(policy['disabled_features']))}.", "",
        "## Calibration comparison", "", "| Method | Eligible | Median top-20 Jaccard | Tracks | Max track share | Reason coverage |", "|---|---:|---:|---:|---:|---:|",
    ]
    for name in ("rule", "empirical_percentile", "robust_mad", "isolation_forest"):
        item = protocol["method_metrics"][name]
        lines.append(f"| {name} | {item['eligible']} | {item['median_top20_jaccard']} | {item['top20_distinct_tracks']} | {item['top20_maximum_track_share']:.3f} | {item['top20_reason_coverage']:.3f} |")
    lines += ["", f"Primary demo candidate: **{protocol['selected_method']}**. Eligibility gate passed: **{protocol['selected_method_eligible']}**.", "", "## Calibration robustness", "", "| Method | Minimum top-20 overlap | Minimum rank correlation |", "|---|---:|---:|"]
    for name in ("rule", "empirical_percentile", "robust_mad", "isolation_forest"):
        item = protocol["robustness"][name]
        lines.append(f"| {name} | {item['minimum_top20_jaccard']:.3f} | {item['minimum_spearman_rank_correlation']:.3f} |")
    lines += ["", "The fixed calibration perturbations cover reference clipping, rule boundaries, Isolation Forest seeds, and Isolation Forest tree counts. They do not use January 3.", "", "## Held-out temporal evaluation", "", "| Method | Review workload | Cutoff exceedances | Tracks | Max track share | Reason coverage |", "|---|---:|---:|---:|---:|---:|"]
    for name in ("rule", "empirical_percentile", "robust_mad", "isolation_forest"):
        item = evaluation["methods"][name]
        lines.append(f"| {name} | {item['exact_review_workload']} | {item['calibration_cutoff_exceedance_count']} | {item['top20_distinct_tracks']} | {item['top20_maximum_track_share']:.3f} | {item['top20_reason_coverage']:.3f} |")
    lines += ["", "## Interpretation limits", "", "- Rankings identify deviations from the January 1 background for human review only.", "- No ground-truth event labels, accuracy, precision, recall, or inferred intent are reported.", "- Overlapping windows and repeated vessel tracks are dependent.", "- January 3 aggregate QA was known from Phase 3A, so this is not a pristine blind evaluation.", "- Isolation Forest reasons are supporting feature evidence, not model attribution.", ""]
    path = _rooted(root, output, REPORT)
    if path.exists() and not overwrite:
        raise FileExistsError(f"report already exists: {path}")
    partial = path.with_name(path.name + ".partial")
    path.parent.mkdir(parents=True, exist_ok=True)
    partial.write_text("\n".join(lines), encoding="utf-8")
    partial.replace(path)
    return path
