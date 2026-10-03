from __future__ import annotations

import pytest


def _straight_track(lon0: float, lat: float, lon1: float, n: int = 20):
    """A straight west→east track at constant latitude with n points."""
    return [(lon0 + (lon1 - lon0) * i / (n - 1), lat) for i in range(n)]


def _sufficient_history(count: int = 10):
    """`count` near-identical straight corridor tracks (tiny lateral jitter)."""
    tracks = []
    for k in range(count):
        jitter = 0.0005 * (1 if k % 2 == 0 else -1)  # ~<60 m lateral, deterministic
        tracks.append(_straight_track(120.0, 22.0 + jitter, 121.0))
    return tracks


# --------------------------------------------------------------------------- #
# Baseline builder
# --------------------------------------------------------------------------- #


def test_build_baseline_sufficient_history() -> None:
    from apps.api.seawatch.trajectories.route_deviation import build_route_baseline

    baseline = build_route_baseline(
        "cellA->cellB", _sufficient_history(10), observed_time_range="2024-01-01/2024-01-14"
    )
    assert baseline.sufficient is True
    assert baseline.contributing_track_count == 10
    assert len(baseline.centerline) == 50
    assert len(baseline.corridor_width_m) == 50
    # Centre-line stays near the median latitude (~22.0).
    assert all(abs(lat - 22.0) < 0.01 for _, lat in baseline.centerline)


def test_build_baseline_insufficient_history_is_not_fabricated() -> None:
    from apps.api.seawatch.trajectories.route_deviation import (
        MIN_BASELINE_TRACKS,
        build_route_baseline,
    )

    baseline = build_route_baseline("cellA->cellB", _sufficient_history(2))
    assert baseline.sufficient is False
    assert baseline.centerline == ()
    assert baseline.corridor_width_m == ()
    assert baseline.contributing_track_count < MIN_BASELINE_TRACKS


def test_build_baseline_ignores_degenerate_single_point_tracks() -> None:
    from apps.api.seawatch.trajectories.route_deviation import build_route_baseline

    history = _sufficient_history(6) + [[(120.5, 22.0)]]  # one 1-point track
    baseline = build_route_baseline("cellA->cellB", history)
    # The degenerate track is dropped; only the 6 usable tracks contribute.
    assert baseline.contributing_track_count == 6
    assert baseline.sufficient is True


# --------------------------------------------------------------------------- #
# Deviation — sufficient baseline
# --------------------------------------------------------------------------- #


def test_on_corridor_track_reports_small_deviation_within_corridor() -> None:
    from apps.api.seawatch.trajectories.route_deviation import (
        build_route_baseline,
        compute_route_deviation,
    )

    baseline = build_route_baseline("cellA->cellB", _sufficient_history(10))
    on_route = _straight_track(120.0, 22.0, 121.0)
    result = compute_route_deviation("trk-ok", on_route, baseline)

    assert result.deviation_distance_m.provenance == "derived"
    assert result.deviation_distance_m.value is not None
    assert result.deviation_distance_m.value < 500.0  # within corridor
    assert result.confidence == "LOW"
    assert result.evidence[0].id == "cross_track"
    assert "within the historical corridor" in result.evidence[0].statement


def test_deviating_track_reports_large_derived_deviation() -> None:
    from apps.api.seawatch.trajectories.route_deviation import (
        build_route_baseline,
        compute_route_deviation,
    )

    baseline = build_route_baseline("cellA->cellB", _sufficient_history(12))
    # Current track detours ~0.1° north of the corridor (~11 km).
    deviating = _straight_track(120.0, 22.1, 121.0)
    result = compute_route_deviation("trk-dev", deviating, baseline)

    assert result.deviation_distance_m.provenance == "derived"
    assert result.deviation_distance_m.value > 5000.0  # kilometres off corridor
    assert result.deviation_ratio.provenance == "derived"
    assert result.deviation_ratio.value > 1.0
    assert result.confidence in {"MEDIUM", "HIGH"}
    assert result.evidence[0].id == "cross_track"
    assert "departs from the historical median corridor" in result.evidence[0].statement
    # No prohibited vocabulary anywhere in the serialized evidence.
    blob = str(result.to_dict()).lower()
    for term in ("suspicious", "threat", "dangerous", "illegal"):
        assert term not in blob


def test_course_offset_supporting_evidence_is_derived() -> None:
    from apps.api.seawatch.trajectories.route_deviation import (
        build_route_baseline,
        compute_route_deviation,
    )

    baseline = build_route_baseline("cellA->cellB", _sufficient_history(12))
    deviating = _straight_track(120.0, 22.1, 121.0)
    # Corridor heading is ~90° (due east); feed a northbound COG (~0°).
    result = compute_route_deviation(
        "trk-dev", deviating, baseline, current_cog=[0.0, 0.0, 0.0]
    )
    offset = [e for e in result.evidence if e.id == "course_offset"]
    assert offset and offset[0].provenance == "derived"
    assert "ΔCOG" in (offset[0].evidence or "")


# --------------------------------------------------------------------------- #
# Deviation — insufficient baseline ⇒ Unknown (never fabricated)
# --------------------------------------------------------------------------- #


def test_insufficient_baseline_yields_unknown_deviation() -> None:
    from apps.api.seawatch.trajectories.route_deviation import (
        build_route_baseline,
        compute_route_deviation,
    )

    baseline = build_route_baseline("cellA->cellB", _sufficient_history(2))
    result = compute_route_deviation("trk-x", _straight_track(120.0, 22.0, 121.0), baseline)

    assert result.deviation_distance_m.value is None
    assert result.deviation_distance_m.provenance == "unknown"
    assert result.deviation_ratio.provenance == "unknown"
    assert result.baseline_source.provenance == "unknown"
    assert result.confidence == "LOW"
    assert result.evidence[0].id == "baseline_insufficient"
    assert result.evidence[0].provenance == "unknown"


def test_current_track_too_short_yields_unknown() -> None:
    from apps.api.seawatch.trajectories.route_deviation import (
        build_route_baseline,
        compute_route_deviation,
    )

    baseline = build_route_baseline("cellA->cellB", _sufficient_history(10))
    result = compute_route_deviation("trk-short", [(120.0, 22.0), (120.1, 22.0)], baseline)
    assert result.deviation_distance_m.provenance == "unknown"
    assert result.evidence[0].id == "baseline_insufficient"


# --------------------------------------------------------------------------- #
# Determinism & provenance correctness
# --------------------------------------------------------------------------- #


def test_deterministic_output() -> None:
    from apps.api.seawatch.trajectories.route_deviation import (
        build_route_baseline,
        compute_route_deviation,
    )

    history = _sufficient_history(12)
    deviating = _straight_track(120.0, 22.1, 121.0)

    a = compute_route_deviation(
        "trk-dev", deviating, build_route_baseline("r", history)
    ).to_dict()
    b = compute_route_deviation(
        "trk-dev", deviating, build_route_baseline("r", history)
    ).to_dict()
    assert a == b


def test_provenance_correctness_across_fields() -> None:
    from apps.api.seawatch.trajectories.route_deviation import (
        build_route_baseline,
        compute_route_deviation,
    )

    baseline = build_route_baseline("r", _sufficient_history(12))
    result = compute_route_deviation(
        "trk-dev", _straight_track(120.0, 22.1, 121.0), baseline, current_cog=[0.0, 0.0]
    )
    d = result.to_dict()
    # Derived metrics when baseline is sufficient.
    assert d["deviation_distance_m"]["provenance"] == "derived"
    assert d["deviation_p95_m"]["provenance"] == "derived"
    assert d["baseline_source"]["provenance"] == "derived"
    # Every evidence item is trajectory-derived and carries a provenance class.
    for item in d["evidence"]:
        assert item["source"] == "trajectory_derived"
        assert item["provenance"] in {"derived", "unknown"}
    assert d["schemaVersion"] == "route-deviation-1"
    assert "human review" in d["disclaimer"].lower()


def test_percentile_is_deterministic_and_interpolates() -> None:
    from apps.api.seawatch.trajectories.route_deviation import _percentile

    assert _percentile([10.0], 0.9) == 10.0
    assert _percentile([0.0, 10.0], 0.5) == pytest.approx(5.0)
    assert _percentile([0.0, 10.0], 0.9) == pytest.approx(9.0)
