"""Alert (review-candidate) response schemas.

Alerts are behavioral review candidates ranked by review priority. They describe
deviations from a statistical background for human review only. They are not
threat assessments, findings of hostility, or determinations of legality, and
this vocabulary is deliberately excluded from the schema and its descriptions.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ExplanationReason(BaseModel):
    """A single feature-derived explanation for why a window was prioritized."""

    reason_code: str = Field(..., description="Stable code for the deviation category.")
    feature_group: str = Field(..., description="Feature family the reason belongs to.")
    feature_name: str = Field(..., description="Underlying movement feature name.")
    observed_value: float = Field(..., description="Observed feature value for the window.")
    unit: str = Field(..., description="Unit of the observed value.")
    reference_percentile: float = Field(
        ...,
        description="Percentile of the observed value against the background distribution.",
    )
    direction: str = Field(..., description="Whether the value is 'higher' or 'lower' than typical.")
    severity: float = Field(..., description="Relative contribution of this reason to the score.")
    message: str = Field(..., description="Human-readable explanation of the deviation.")
    attribution_kind: str = Field(
        ...,
        description="'exact_component' or 'supporting_evidence' (not model attribution).",
    )


class SupportingFeature(BaseModel):
    """A movement feature value that supports the explanation."""

    feature_name: str = Field(..., description="Underlying movement feature name.")
    feature_group: str = Field(..., description="Feature family the feature belongs to.")
    observed_value: float = Field(..., description="Observed feature value for the window.")
    unit: str = Field(..., description="Unit of the observed value.")
    reference_percentile: float = Field(
        ...,
        description="Percentile of the observed value against the background distribution.",
    )


class DataQuality(BaseModel):
    """Window-level data-quality context for interpreting a review candidate."""

    observation_count: int = Field(..., description="Number of AIS observations in the window.", ge=0)
    observed_duration_seconds: float = Field(
        ...,
        description="Observed window duration in seconds.",
        ge=0.0,
    )
    max_gap_seconds: float | None = Field(
        default=None,
        description="Largest observation gap in the window, in seconds.",
    )
    sog_valid_fraction: float | None = Field(
        default=None,
        description="Fraction of speed-over-ground values that are valid.",
    )
    cog_valid_fraction: float | None = Field(
        default=None,
        description="Fraction of course-over-ground values that are valid.",
    )


class AlertSummary(BaseModel):
    """Compact ranked review candidate for the /alerts collection."""

    alert_id: str = Field(..., description="Stable surrogate identifier for the review candidate.")
    track_id: str = Field(..., description="Date-scoped surrogate track identifier.")
    date: str = Field(..., description="Source date (ISO 8601) the candidate belongs to.")
    ranking_score: float = Field(..., description="Review priority score (ranking value, not a probability).")
    ranking_method: str = Field(..., description="Ranking method that produced the score.")
    rank: int = Field(..., description="Rank within the date and method (1 = highest priority).", ge=1)
    shortlisted: bool = Field(..., description="Whether the candidate is within the review budget.")
    explanation_reasons: list[ExplanationReason] = Field(default_factory=list)

    model_config = {
        "json_schema_extra": {
            "example": {
                "alert_id": "2024-01-03__isolation_forest__t-000042__w-0007",
                "track_id": "2024-01-03__t-000042",
                "date": "2024-01-03",
                "ranking_score": 87.42,
                "ranking_method": "isolation_forest",
                "rank": 3,
                "shortlisted": True,
                "explanation_reasons": [
                    {
                        "reason_code": "speed_higher",
                        "feature_group": "speed",
                        "feature_name": "sog_mean",
                        "observed_value": 14.2,
                        "unit": "knots",
                        "reference_percentile": 0.985,
                        "direction": "higher",
                        "severity": 2.31,
                        "message": "Sog mean is at the 98.5th percentile the January 1 background.",
                        "attribution_kind": "supporting_evidence",
                    }
                ],
            }
        }
    }


class AlertListResponse(BaseModel):
    """Envelope for the ranked review-candidate collection.

    ``count`` is the number of items returned in this page. ``total`` is the
    number of candidates matching the filters before pagination. List items omit
    heavy ``explanation_reasons``; load those via ``GET /alerts/{alert_id}``.
    """

    count: int = Field(..., description="Number of alerts returned in this page.", ge=0)
    total: int = Field(..., description="Total candidates matching the filters.", ge=0)
    limit: int = Field(..., description="Page size applied.", ge=0)
    offset: int = Field(..., description="Offset applied.", ge=0)
    alerts: list[AlertSummary] = Field(default_factory=list)


class AlertDetail(BaseModel):
    """Full review candidate: ranking result, explanation, features, data quality."""

    alert_id: str = Field(..., description="Stable surrogate identifier for the review candidate.")
    track_id: str = Field(..., description="Date-scoped surrogate track identifier.")
    date: str = Field(..., description="Source date (ISO 8601) the candidate belongs to.")
    ranking_score: float = Field(..., description="Review priority score (ranking value, not a probability).")
    ranking_method: str = Field(..., description="Ranking method that produced the score.")
    rank: int = Field(..., description="Rank within the date and method (1 = highest priority).", ge=1)
    shortlisted: bool = Field(..., description="Whether the candidate is within the review budget.")
    review_status: str = Field(..., description="Current human review status.")
    explanation_reasons: list[ExplanationReason] = Field(default_factory=list)
    supporting_features: list[SupportingFeature] = Field(default_factory=list)
    data_quality: DataQuality = Field(..., description="Window-level data-quality context.")
