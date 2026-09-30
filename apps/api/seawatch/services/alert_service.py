"""Alert (review-candidate) service.

Reads the existing Phase 3B ranking artifacts and projects them to review-priority
alerts with feature-derived explanations. No ranking is recomputed here.
"""

from __future__ import annotations

from dataclasses import dataclass
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


def _summary_from_row(row: dict, *, include_reasons: bool = False) -> AlertSummary:
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
        # List items are intentionally slim: full explanation_reasons are loaded
        # only via GET /alerts/{alert_id}. Kept as an empty list for a stable shape.
        explanation_reasons=_parse_reasons(row.get("evidence_reasons")) if include_reasons else [],
    )


def _detail_from_row(row: dict) -> AlertDetail:
    summary = _summary_from_row(row, include_reasons=True)
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


def _method_column(frame: pd.DataFrame) -> pd.Series:
    if "method_id" in frame.columns:
        return frame["method_id"].astype("string")
    if "ranking_method" in frame.columns:
        return frame["ranking_method"].astype("string")
    return pd.Series([""] * len(frame), index=frame.index, dtype="string")


@dataclass(frozen=True)
class AlertPage:
    """A page of ranked review candidates plus the pre-pagination total."""

    items: list[AlertSummary]
    total: int


def list_alerts(
    *,
    method: str | None = None,
    shortlisted_only: bool = False,
    dedupe_by_track: bool = False,
    limit: int | None = None,
    offset: int = 0,
    use_cache: bool = True,
) -> AlertPage:
    """Return a page of ranked review candidates.

    Filtering, sorting, deduplication, and pagination are performed on the cached
    ranking frame (no re-read of the Parquet artifact). Only the returned page is
    converted to schema objects, and list summaries omit explanation_reasons.

    Args:
        method: Restrict to a single ranking method (e.g. the primary method).
        shortlisted_only: Keep only candidates within the review budget.
        dedupe_by_track: Keep only the highest-priority window per track.
        limit: Maximum items to return (None = all matching).
        offset: Number of leading items to skip.

    Raises:
        MissingArtifactError: If no Phase 3B ranking artifact exists.
    """

    frame = load_ranking_frame(use_cache=use_cache)

    if method:
        frame = frame.loc[_method_column(frame) == str(method)]
    if shortlisted_only and "shortlisted" in frame.columns:
        frame = frame.loc[frame["shortlisted"].astype(bool)]

    sort_keys = [name for name in ("review_priority_score",) if name in frame.columns]
    if sort_keys:
        frame = frame.sort_values(sort_keys, ascending=False, kind="mergesort")

    if dedupe_by_track and "track_id" in frame.columns:
        # Rows are already sorted by descending priority, so the first row per
        # track is its highest-priority window.
        frame = frame.drop_duplicates(subset="track_id", keep="first")

    total = int(len(frame))

    start = max(0, offset)
    page = frame.iloc[start : start + limit] if limit is not None else frame.iloc[start:]
    items = [_summary_from_row(row) for row in page.to_dict(orient="records")]
    return AlertPage(items=items, total=total)


def get_alert(alert_id: str, *, use_cache: bool = True) -> AlertDetail | None:
    """Return the full review candidate for ``alert_id`` or None if not found.

    Raises:
        MissingArtifactError: If no Phase 3B ranking artifact exists.
    """

    frame = load_ranking_frame(use_cache=use_cache)
    methods = _method_column(frame)
    for position, row in enumerate(frame.to_dict(orient="records")):
        candidate_id = build_alert_id(
            str(row.get("source_date", "")),
            str(methods.iloc[position]) if position < len(methods) else _method_of(row),
            str(row.get("track_id", "")),
            str(row.get("window_id", "")),
        )
        if candidate_id == alert_id:
            return _detail_from_row(row)
    return None
