"""WGS84 geodesic and circular-angle primitives for trajectories."""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np
import pandas as pd
from pyproj import Geod


WGS84_GEOD = Geod(ellps="WGS84")


@dataclass(frozen=True)
class PathMetrics:
    path_distance_m: float | None
    displacement_m: float | None
    path_displacement_ratio: float | None


def geodesic_distance_m(
    lon1: float, lat1: float, lon2: float, lat2: float
) -> float:
    """Return non-negative WGS84 geodesic distance in metres."""

    _, _, distance = WGS84_GEOD.inv(lon1, lat1, lon2, lat2)
    return abs(float(distance))


def consecutive_geodesic_distances_m(
    longitude: pd.Series, latitude: pd.Series
) -> pd.Series:
    """Return distances between adjacent positions in their existing order."""

    if len(longitude) != len(latitude):
        raise ValueError("longitude and latitude lengths must match")
    if len(longitude) < 2:
        return pd.Series(dtype=float)
    lon = pd.to_numeric(longitude, errors="coerce").to_numpy(dtype=float)
    lat = pd.to_numeric(latitude, errors="coerce").to_numpy(dtype=float)
    _, _, distances = WGS84_GEOD.inv(lon[:-1], lat[:-1], lon[1:], lat[1:])
    return pd.Series(np.abs(distances), dtype=float)


def circular_difference_degrees(start: object, end: object) -> float:
    """Return the shortest signed angular change from start to end."""

    if pd.isna(start) or pd.isna(end):
        return math.nan
    return (float(end) - float(start) + 180.0) % 360.0 - 180.0


def path_metrics(
    longitude: pd.Series,
    latitude: pd.Series,
    *,
    minimum_displacement_m: float,
) -> PathMetrics:
    """Summarize path length, endpoint displacement, and stable ratio."""

    if minimum_displacement_m < 0:
        raise ValueError("minimum_displacement_m must be non-negative")
    if len(longitude) != len(latitude):
        raise ValueError("longitude and latitude lengths must match")
    if len(longitude) < 2:
        return PathMetrics(None, None, None)
    lon = pd.to_numeric(longitude, errors="coerce").to_numpy(dtype=float)
    lat = pd.to_numeric(latitude, errors="coerce").to_numpy(dtype=float)
    if not np.isfinite(lon).all() or not np.isfinite(lat).all():
        return PathMetrics(None, None, None)
    distances = consecutive_geodesic_distances_m(
        pd.Series(lon), pd.Series(lat)
    )
    path_distance = float(distances.sum())
    displacement = geodesic_distance_m(lon[0], lat[0], lon[-1], lat[-1])
    ratio = (
        path_distance / displacement
        if displacement >= minimum_displacement_m and displacement > 0
        else None
    )
    return PathMetrics(path_distance, displacement, ratio)
