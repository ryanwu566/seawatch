"""Alert (review-candidate) service.

Reads the existing Phase 3B ranking artifacts and projects them to review-priority
alerts with feature-derived explanations. No ranking is recomputed here.
"""

from __future__ import annotations

import json

import pandas as pd

from ..schemas.alert import (
    AlertDetail,
    AlertSummary,
    DataQuality,
    ExplanationReason,
    SupportingFeature,
)
from .artifacts import load_ranking_frame

_ID_SEPARATOR = "__"


def build_alert_id(date: str, method: str, track_id: str, window_id: str) -> str:
    """Compose the stable surrogate alert identifier."""

    return _ID_SEPARATOR.join((str(date), str(method), str(track_id), str(window_id)))


def _as_float(value: object, default: float = 0.0) -> float:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_optional_float(value: object) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: object, default: int = 0) -> int:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _parse_reasons(raw: object) -> list[ExplanationReason]:
    """Parse the ``evidence_reasons`` JSON string into explanation reasons."""

    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return []
    if isinstance(raw, str):
        if not raw.strip():
            return []
        try:
            items = json.loads(raw)
        except json.JSONDecodeError:
            return []
    elif isinstance(raw, (list, tuple)):
        items = list(raw)
    else:
        return []
    reasons: list[ExplanationReason] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        reasons.append(
            ExplanationReason(
                reason_code=str(item.get("reason_code", "")),
                feature_group=str(item.get("feature_group", "")),
                feature_name=str(item.get("feature_name", "")),
                observed_value=_as_float(item.get("observed_value")),
                unit=str(item.get("unit", "")),
                reference_percentile=_as_float(item.get("reference_percentile")),
                direction=str(item.get("direction", "")),
                severity=_as_float(item.get("severity")),
                message=str(item.get("message", "")),
                attribution_kind=str(item.get("attribution_kind", "")),
            )
        )
    return reasons


def _method_of(row: dict) -> str:
    return str(row.get("method_id", row.get("ranking_method", "")))


def _summary_from_row(row: dict) -> AlertSummary:
    date = str(row.get("source_date", ""))
    method = _method_of(row)
    track_id = str(row.get("track_id", ""))
    window_id = str(row.get("window_id", ""))
    return AlertSummary(
        alert_id=build_alert_id(date, method, track_id, window_id),
        track_id=track_id,
        date=date,
        ranking_score=_as_float(row.get("review_priority_score")),
        ranking_method=method,
        rank=max(1, _as_int(row.get("rank_within_date_method"), default=1)),
        shortlisted=bool(row.get("shortlisted", False)),
        explanation_reasons=_parse_reasons(row.get("evidence_reasons")),
    )


def _detail_from_row(row: dict) -> AlertDetail:
    summary = _summary_from_row(row)
    supporting = [
        SupportingFeature(
            feature_name=reason.feature_name,
            feature_group=reason.feature_group,
            observed_value=reason.observed_value,
            unit=reason.unit,
            reference_percentile=reason.reference_percentile,
        )
        for reason in summary.explanation_reasons
    ]
    data_quality = DataQuality(
        observation_count=_as_int(row.get("observation_count")),
        observed_duration_seconds=_as_float(row.get("observed_duration_seconds")),
        max_gap_seconds=_as_optional_float(row.get("max_gap_seconds")),
        sog_valid_fraction=_as_optional_float(row.get("sog_valid_fraction")),
        cog_valid_fraction=_as_optional_float(row.get("cog_valid_fraction")),
    )
    return AlertDetail(
        alert_id=summary.alert_id,
        track_id=summary.track_id,
        date=summary.date,
        ranking_score=summary.ranking_score,
        ranking_method=summary.ranking_method,
        rank=summary.rank,
        shortlisted=summary.shortlisted,
        review_status=str(row.get("review_status", "unreviewed")),
        explanation_reasons=summary.explanation_reasons,
        supporting_features=supporting,
        data_quality=data_quality,
    )


def _ordered_rows(*, use_cache: bool) -> list[dict]:
    frame = load_ranking_frame(use_cache=use_cache)
    sort_keys = [name for name in ("review_priority_score",) if name in frame.columns]
    if sort_keys:
        frame = frame.sort_values(sort_keys, ascending=False, kind="mergesort")
    return frame.to_dict(orient="records")


def list_alerts(*, shortlisted_only: bool = False, use_cache: bool = True) -> list[AlertSummary]:
    """Return ranked review candidates ordered by descending review priority.

    Raises:
        MissingArtifactError: If no Phase 3B ranking artifact exists.
    """

    rows = _ordered_rows(use_cache=use_cache)
    summaries = [_summary_from_row(row) for row in rows]
    if shortlisted_only:
        summaries = [item for item in summaries if item.shortlisted]
    return summaries


def get_alert(alert_id: str, *, use_cache: bool = True) -> AlertDetail | None:
    """Return the full review candidate for ``alert_id`` or None if not found.

    Raises:
        MissingArtifactError: If no Phase 3B ranking artifact exists.
    """

    rows = _ordered_rows(use_cache=use_cache)
    for row in rows:
        candidate_id = build_alert_id(
            str(row.get("source_date", "")),
            _method_of(row),
            str(row.get("track_id", "")),
            str(row.get("window_id", "")),
        )
        if candidate_id == alert_id:
            return _detail_from_row(row)
    return None
