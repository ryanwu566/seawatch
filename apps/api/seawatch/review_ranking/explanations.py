"""Deterministic, feature-derived explanation templates."""

from __future__ import annotations

from .config import Phase3BConfig
from .contracts import EvidenceReason, TransformedFeatures


def build_evidence_reasons(method_id: str, score_components, features: TransformedFeatures, config: Phase3BConfig) -> list[tuple[EvidenceReason, ...]]:
    attribution = "supporting_evidence" if method_id == "isolation_forest" else "exact_component"
    group_for = {name: group for group, names in config.feature_groups.items() for name in names}
    output: list[tuple[EvidenceReason, ...]] = []
    for index in features.raw.index:
        ordered = sorted(features.feature_names, key=lambda name: (-float(score_components.loc[index, name]), name))
        selected: list[str] = []
        seen_groups: set[str] = set()
        for name in ordered:
            group = group_for[name]
            if group not in seen_groups:
                selected.append(name)
                seen_groups.add(group)
            if len(selected) == config.rules.max_reasons:
                break
        reasons: list[EvidenceReason] = []
        for name in selected:
            percentile = float(features.percentiles.loc[index, name])
            direction = "higher" if percentile >= 0.5 else "lower"
            comparison = f"at the {percentile * 100:.1f}th percentile" if direction == "higher" else f"below {100 * (1 - percentile):.1f}% of"
            message = f"{name.replace('_', ' ').capitalize()} is {comparison} the January 1 background."
            if attribution == "supporting_evidence":
                message += " This is supporting feature evidence, not model attribution."
            reasons.append(EvidenceReason(
                reason_code=f"{group_for[name]}_{direction}", feature_group=group_for[name], feature_name=name,
                observed_value=float(features.raw.loc[index, name]), unit=config.feature_units[name], reference_percentile=percentile,
                direction=direction, severity=float(score_components.loc[index, name]), message=message, attribution_kind=attribution,
            ))
        output.append(tuple(reasons))
    return output
