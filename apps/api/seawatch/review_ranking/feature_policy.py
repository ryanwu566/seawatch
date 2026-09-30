"""Pre-model feature support analysis using train and calibration only."""

from __future__ import annotations

import hashlib
import json
from typing import Any

import numpy as np

from .config import Phase3BConfig
from .contracts import FeaturePolicyAnalysis, SplitWindows


def _support(split: SplitWindows, name: str) -> dict[str, float | int]:
    values = split.frame[name].to_numpy(dtype=float)
    finite = np.isfinite(values)
    return {
        "finite_count": int(finite.sum()),
        "finite_fraction": float(finite.mean()) if len(values) else 0.0,
        "track_count": int(split.frame.loc[finite, "track_id"].nunique()),
        "distinct_count": int(np.unique(values[finite]).size),
    }


def analyze_feature_policy(train: SplitWindows, calibration: SplitWindows, config: Phase3BConfig) -> FeaturePolicyAnalysis:
    if (train.split_role, calibration.split_role) != ("train", "calibration"):
        raise ValueError("feature policy requires train and calibration roles")
    expected = (config.split_dates["train"], config.split_dates["calibration"])
    if (train.source_date.isoformat(), calibration.source_date.isoformat()) != expected:
        raise ValueError("feature policy split dates do not match configuration")
    support: dict[str, dict[str, Any]] = {}
    disabled: dict[str, str] = {}
    active: list[str] = []
    for name in config.tier_a + config.tier_b + config.tier_c:
        if name not in train.frame or name not in calibration.frame:
            raise ValueError(f"missing configured feature: {name}")
        tr, ca = _support(train, name), _support(calibration, name)
        support[name] = {"train": tr, "calibration": ca}
        if name in config.tier_c:
            disabled[name] = "tier_c_excluded"
        elif name in config.tier_a:
            if tr["finite_fraction"] < config.support.tier_a_min_fraction or ca["finite_fraction"] < config.support.tier_a_min_fraction or tr["distinct_count"] < 2:
                raise ValueError(f"Tier A feature is ineligible: {name}")
            active.append(name)
        else:
            passed = (
                tr["finite_fraction"] >= config.support.tier_b_min_fraction
                and ca["finite_fraction"] >= config.support.tier_b_min_fraction
                and tr["finite_count"] >= config.support.tier_b_min_windows
                and ca["finite_count"] >= config.support.tier_b_min_windows
                and tr["track_count"] >= config.support.tier_b_min_tracks
                and ca["track_count"] >= config.support.tier_b_min_tracks
                and abs(float(tr["finite_fraction"]) - float(ca["finite_fraction"])) <= config.support.tier_b_max_role_gap
                and tr["distinct_count"] >= 2
            )
            if passed:
                active.append(name)
            else:
                disabled[name] = "conditional_support_gate_failed"
    payload = {"active_features": active, "disabled_features": disabled, "support": support}
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    return FeaturePolicyAnalysis(tuple(active), disabled, support, digest)


def feature_policy_payload(analysis: FeaturePolicyAnalysis, *, input_hashes: dict[str, str], config_sha256: str) -> dict[str, object]:
    return {"schema_version": "phase3b-feature-policy-v1", "policy_hash": analysis.policy_hash, "active_features": list(analysis.active_features), "disabled_features": dict(analysis.disabled_features), "support": analysis.support, "input_hashes": input_hashes, "config_sha256": config_sha256}
