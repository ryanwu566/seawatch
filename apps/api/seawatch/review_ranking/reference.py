"""Train-only empirical reference fitting and transformation."""

from __future__ import annotations

import hashlib
import json

import numpy as np
import pandas as pd

from .config import Phase3BConfig
from .contracts import FeaturePolicyAnalysis, FeatureReference, ReferenceProfile, SplitWindows, TransformedFeatures


def empirical_midrank(values: np.ndarray, reference_sorted: np.ndarray) -> np.ndarray:
    reference = np.asarray(reference_sorted, dtype=float)
    if reference.ndim != 1 or reference.size == 0 or not np.isfinite(reference).all():
        raise ValueError("reference distribution must be finite and non-empty")
    raw = np.asarray(values, dtype=float)
    left = np.searchsorted(reference, raw, side="left")
    right = np.searchsorted(reference, raw, side="right")
    return (left + 0.5 * (right - left)) / reference.size


def fit_reference_profile(train: SplitWindows, policy: FeaturePolicyAnalysis, config: Phase3BConfig) -> ReferenceProfile:
    if train.split_role != "train" or train.source_date.isoformat() != config.split_dates["train"]:
        raise ValueError("reference profile can only be fitted on configured train data")
    refs: dict[str, FeatureReference] = {}
    serial: dict[str, object] = {}
    for name in policy.active_features:
        values = train.frame[name].to_numpy(dtype=float)
        values = values[np.isfinite(values)]
        if values.size == 0:
            raise ValueError(f"no finite training values for {name}")
        q1, q3 = np.quantile(values, [0.25, 0.75])
        median = float(np.median(values))
        iqr = float(q3 - q1)
        mad = float(np.median(np.abs(values - median)))
        if iqr > 0:
            scale, method = iqr / 1.349, "iqr"
        elif mad > 0:
            scale, method = 1.4826 * mad, "mad"
        else:
            scale, method = 1.0, "inactive_zero_dispersion"
        low, high = np.quantile(values, [config.reference.clip_low_quantile, config.reference.clip_high_quantile])
        ref = FeatureReference(float(low), float(high), median, float(scale), method, np.sort(values))
        refs[name] = ref
        serial[name] = {"clip_low": ref.clip_low, "clip_high": ref.clip_high, "median": median, "scale": scale, "scale_method": method, "finite_count": len(values)}
    digest = hashlib.sha256(json.dumps(serial, sort_keys=True).encode()).hexdigest()
    return ReferenceProfile(policy.active_features, refs, digest)


def transform_with_reference(frame: pd.DataFrame, profile: ReferenceProfile) -> TransformedFeatures:
    raw = frame.loc[:, list(profile.feature_names)].apply(pd.to_numeric, errors="coerce").astype(float)
    missing = ~np.isfinite(raw)
    if missing.any().any():
        raise ValueError("missing core or active feature values are not imputed")
    clipped, scaled, percentiles = raw.copy(), raw.copy(), raw.copy()
    for name in profile.feature_names:
        ref = profile.features[name]
        clipped[name] = raw[name].clip(ref.clip_low, ref.clip_high)
        scaled[name] = 0.0 if ref.scale_method == "inactive_zero_dispersion" else (clipped[name] - ref.median) / ref.scale
        percentiles[name] = empirical_midrank(raw[name].to_numpy(), ref.reference_sorted)
    return TransformedFeatures(profile.feature_names, raw, clipped, scaled, percentiles, missing)


def reference_profile_payload(profile: ReferenceProfile, *, train_hash: str, policy_hash: str, config_hash: str) -> dict[str, object]:
    return {"reference_hash": profile.reference_hash, "train_hash": train_hash, "policy_hash": policy_hash, "config_hash": config_hash, "feature_names": list(profile.feature_names)}
