"""Slice A — provenance rule tests for the logistics module."""

from __future__ import annotations

import pytest

from apps.api.seawatch.logistics.models import (
    DecisionBrief,
    Port,
    Route,
    SourceMetadata,
    SourceType,
)
from apps.api.seawatch.logistics.provenance import (
    carries_note,
    summarize,
    validate_official,
)


def _port(source_type: SourceType, metadata: SourceMetadata | None = None) -> Port:
    return Port(
        id="kaohsiung",
        name_zh="高雄港",
        name_en="Kaohsiung",
        lon=120.3,
        lat=22.6,
        capacity_units=0.0,
        base_handling_cost=1.0,
        source_type=source_type,
        source_metadata=metadata,
    )


def _brief(note: str) -> DecisionBrief:
    return DecisionBrief(
        scenario_id="s",
        summary_zh="",
        summary_en="",
        recommended_allocations=(),
        alternatives=(),
        trade_offs=(),
        unmet_demand=(),
        provenance_note=note,
        assumptions=(),
        provenance_summary={},
    )


def test_summarize_counts_each_class() -> None:
    records = [
        _port(SourceType.SCENARIO),
        _port(SourceType.SCENARIO),
        _port(SourceType.SYNTHETIC),
        _port(
            SourceType.OFFICIAL,
            SourceMetadata(source_name="MarineCadastre", source_reference="https://example"),
        ),
    ]
    counts = summarize(records)
    assert counts == {"official": 1, "derived": 0, "scenario": 2, "synthetic": 1}


def test_summarize_shape_is_stable_for_empty() -> None:
    assert summarize([]) == {"official": 0, "derived": 0, "scenario": 0, "synthetic": 0}


def test_carries_note_true_for_nonempty() -> None:
    assert carries_note(_brief("scenario-based planning estimates for human review")) is True


def test_carries_note_false_for_empty_or_blank() -> None:
    assert carries_note(_brief("")) is False
    assert carries_note(_brief("   ")) is False


def test_validate_official_rejects_missing_metadata() -> None:
    with pytest.raises(ValueError):
        validate_official(_port(SourceType.OFFICIAL, None))


def test_validate_official_rejects_incomplete_metadata() -> None:
    with pytest.raises(ValueError):
        validate_official(
            _port(SourceType.OFFICIAL, SourceMetadata(source_name="only name"))
        )


def test_validate_official_accepts_complete_metadata() -> None:
    validate_official(
        _port(
            SourceType.OFFICIAL,
            SourceMetadata(
                source_name="MarineCadastre",
                source_reference="https://marinecadastre.gov",
                as_of="2024",
            ),
        )
    )


def test_validate_derived_requires_method() -> None:
    bad = Route(
        id="r",
        from_port="a",
        to_demand_node="b",
        distance_km=1.0,
        baseline_eta_hours=1.0,
        per_unit_cost=1.0,
        route_risk=0.1,
        source_type=SourceType.DERIVED,
        source_metadata=None,
    )
    with pytest.raises(ValueError):
        validate_official(bad)


def test_validate_derived_accepts_named_method() -> None:
    ok = Route(
        id="r",
        from_port="a",
        to_demand_node="b",
        distance_km=1.0,
        baseline_eta_hours=1.0,
        per_unit_cost=1.0,
        route_risk=0.1,
        source_type=SourceType.DERIVED,
        source_metadata=SourceMetadata(derivation_method="great-circle"),
    )
    validate_official(ok)


def test_scenario_and_synthetic_need_no_metadata() -> None:
    validate_official(_port(SourceType.SCENARIO))
    validate_official(_port(SourceType.SYNTHETIC))
