from __future__ import annotations

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.run_route_deviation_demo import run_demo, synthetic_corridor

# A path that never exists, so run_demo() uses the committed synthetic corridor
# fixture. This keeps the numeric assertions deterministic regardless of whether
# a prepared NOAA Parquet happens to exist on the machine running the tests.
NO_PARQUET = Path("data/processed/features/__does_not_exist__.parquet")


def test_demo_runs_three_scenarios() -> None:
    payload = run_demo(NO_PARQUET)
    scenarios = payload["scenarios"]
    assert set(scenarios) == {
        "A_normal_route",
        "B_route_deviation",
        "C_insufficient_baseline",
    }
    assert payload["demo"] == "route-deviation-1"
    assert payload["data_source"] == "synthetic_demo_corridor"
    assert "human review" in payload["disclaimer"].lower()


def test_scenario_a_normal_is_within_corridor() -> None:
    a = run_demo(NO_PARQUET)["scenarios"]["A_normal_route"]
    assert a["deviation_distance_m"]["provenance"] == "derived"
    assert a["deviation_distance_m"]["value"] is not None
    assert a["deviation_distance_m"]["value"] < 500.0
    assert a["confidence"] == "LOW"
    assert "within the historical corridor" in a["evidence"][0]["statement"]


def test_scenario_b_deviation_is_detected_and_derived() -> None:
    b = run_demo(NO_PARQUET)["scenarios"]["B_route_deviation"]
    assert b["deviation_distance_m"]["provenance"] == "derived"
    assert b["deviation_distance_m"]["value"] > 5000.0
    assert b["deviation_ratio"]["provenance"] == "derived"
    assert b["deviation_ratio"]["value"] > 1.0
    assert b["confidence"] in {"MEDIUM", "HIGH"}
    assert "departs from the historical median corridor" in b["evidence"][0]["statement"]


def test_scenario_c_insufficient_baseline_is_unknown() -> None:
    c = run_demo(NO_PARQUET)["scenarios"]["C_insufficient_baseline"]
    assert c["deviation_distance_m"]["value"] is None
    assert c["deviation_distance_m"]["provenance"] == "unknown"
    assert c["deviation_ratio"]["provenance"] == "unknown"
    assert c["baseline_source"]["provenance"] == "unknown"
    assert c["evidence"][0]["id"] == "baseline_insufficient"


def test_demo_is_deterministic() -> None:
    assert run_demo(NO_PARQUET) == run_demo(NO_PARQUET)


def test_demo_contains_required_fields_and_no_prohibited_wording() -> None:
    payload = run_demo(NO_PARQUET)
    for scenario in payload["scenarios"].values():
        for key in (
            "route_key",
            "baseline_source",
            "deviation_distance_m",
            "deviation_ratio",
            "confidence",
            "evidence",
        ):
            assert key in scenario
    blob = str(payload).lower()
    for term in ("suspicious", "threat", "dangerous", "illegal"):
        assert term not in blob


def test_prepared_or_synthetic_both_yield_valid_three_scenarios() -> None:
    """Auto-detect path (prepared NOAA if present, else synthetic) still yields
    a valid three-scenario payload with the Unknown case intact."""
    payload = run_demo()  # no override: real auto-detection
    assert payload["data_source"] in {
        "prepared_noaa_segmented",
        "synthetic_demo_corridor",
    }
    c = payload["scenarios"]["C_insufficient_baseline"]
    assert c["deviation_distance_m"]["provenance"] == "unknown"
    b = payload["scenarios"]["B_route_deviation"]
    assert b["deviation_distance_m"]["provenance"] == "derived"


def test_synthetic_corridor_shape_is_reproducible() -> None:
    c1 = synthetic_corridor()
    c2 = synthetic_corridor()
    assert c1 == c2
    assert len(c1["history"]) >= 5
    assert len(c1["sparse_history"]) == 2
