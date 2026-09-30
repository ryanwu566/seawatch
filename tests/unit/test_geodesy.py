from __future__ import annotations

import math

import pandas as pd
import pytest


def test_wgs84_geodesic_distance_matches_known_equatorial_distance() -> None:
    from apps.api.seawatch.trajectories.geodesy import geodesic_distance_m

    assert geodesic_distance_m(0.0, 0.0, 0.0, 0.0) == 0.0
    assert geodesic_distance_m(0.0, 0.0, 0.01, 0.0) == pytest.approx(
        1113.1949, rel=1e-5
    )


def test_circular_difference_uses_shortest_signed_change() -> None:
    from apps.api.seawatch.trajectories.geodesy import circular_difference_degrees

    assert circular_difference_degrees(359.0, 1.0) == pytest.approx(2.0)
    assert circular_difference_degrees(1.0, 359.0) == pytest.approx(-2.0)
    assert abs(circular_difference_degrees(0.0, 180.0)) == 180.0
    assert math.isnan(circular_difference_degrees(None, 20.0))


def test_consecutive_distances_are_metre_values_between_adjacent_points() -> None:
    from apps.api.seawatch.trajectories.geodesy import (
        consecutive_geodesic_distances_m,
    )

    result = consecutive_geodesic_distances_m(
        pd.Series([0.0, 0.01, 0.02]), pd.Series([0.0, 0.0, 0.0])
    )

    assert result.tolist() == pytest.approx([1113.1949, 1113.1949], rel=1e-5)


def test_straight_path_has_ratio_near_one() -> None:
    from apps.api.seawatch.trajectories.geodesy import path_metrics

    result = path_metrics(
        pd.Series([0.0, 0.01, 0.02]),
        pd.Series([0.0, 0.0, 0.0]),
        minimum_displacement_m=50.0,
    )

    assert result.path_distance_m == pytest.approx(2226.3898, rel=1e-5)
    assert result.displacement_m == pytest.approx(2226.3898, rel=1e-5)
    assert result.path_displacement_ratio == pytest.approx(1.0, rel=1e-8)


def test_return_to_start_has_positive_path_and_null_ratio() -> None:
    from apps.api.seawatch.trajectories.geodesy import path_metrics

    result = path_metrics(
        pd.Series([0.0, 0.01, 0.0]),
        pd.Series([0.0, 0.0, 0.0]),
        minimum_displacement_m=50.0,
    )

    assert result.path_distance_m == pytest.approx(2226.3898, rel=1e-5)
    assert result.displacement_m == 0.0
    assert result.path_displacement_ratio is None


def test_tiny_displacement_and_one_point_do_not_create_unstable_metrics() -> None:
    from apps.api.seawatch.trajectories.geodesy import path_metrics

    tiny = path_metrics(
        pd.Series([0.0, 0.0001]),
        pd.Series([0.0, 0.0]),
        minimum_displacement_m=50.0,
    )
    one = path_metrics(
        pd.Series([0.0]), pd.Series([0.0]), minimum_displacement_m=50.0
    )

    assert tiny.path_distance_m == pytest.approx(11.1319, rel=1e-4)
    assert tiny.path_displacement_ratio is None
    assert one.path_distance_m is None
    assert one.displacement_m is None
    assert one.path_displacement_ratio is None
