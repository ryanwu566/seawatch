"""Small, dependency-light geodesy helpers (numpy only) for the detection stack."""

from __future__ import annotations

import math

import numpy as np

EARTH_RADIUS_M = 6_371_008.8
NM_M = 1852.0


def haversine_m(lat1, lon1, lat2, lon2):
    """Great-circle distance in metres. Accepts scalars or numpy arrays."""

    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi = p2 - p1
    dlmb = np.radians(np.asarray(lon2) - np.asarray(lon1))
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_M * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))


def haversine_nm(lat1, lon1, lat2, lon2):
    return haversine_m(lat1, lon1, lat2, lon2) / NM_M


def project_xy_m(lat, lon, lat0: float = 23.5, lon0: float = 120.5):
    """Local equirectangular projection (metres) - accurate enough at Taiwan scale."""

    lat = np.asarray(lat, dtype=float)
    lon = np.asarray(lon, dtype=float)
    x = np.radians(lon - lon0) * EARTH_RADIUS_M * math.cos(math.radians(lat0))
    y = np.radians(lat - lat0) * EARTH_RADIUS_M
    return x, y


def bearing_deg(lat1, lon1, lat2, lon2):
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dl = np.radians(np.asarray(lon2) - np.asarray(lon1))
    y = np.sin(dl) * np.cos(p2)
    x = np.cos(p1) * np.sin(p2) - np.sin(p1) * np.cos(p2) * np.cos(dl)
    return (np.degrees(np.arctan2(y, x)) + 360.0) % 360.0


def destination(lat: float, lon: float, bearing: float, distance_m: float) -> tuple[float, float]:
    """Point reached travelling ``distance_m`` along ``bearing`` (degrees)."""

    d = distance_m / EARTH_RADIUS_M
    b = math.radians(bearing)
    p1, l1 = math.radians(lat), math.radians(lon)
    p2 = math.asin(math.sin(p1) * math.cos(d) + math.cos(p1) * math.sin(d) * math.cos(b))
    l2 = l1 + math.atan2(math.sin(b) * math.sin(d) * math.cos(p1), math.cos(d) - math.sin(p1) * math.sin(p2))
    return math.degrees(p2), (math.degrees(l2) + 540.0) % 360.0 - 180.0


def point_in_polygon(lat: float, lon: float, polygon: list[tuple[float, float]]) -> bool:
    """Ray casting; polygon is a list of (lat, lon) vertices."""

    inside = False
    n = len(polygon)
    j = n - 1
    for i in range(n):
        yi, xi = polygon[i]
        yj, xj = polygon[j]
        if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi + 1e-18) + xi:
            inside = not inside
        j = i
    return inside


def points_in_polygon(lat: np.ndarray, lon: np.ndarray, polygon: list[tuple[float, float]]) -> np.ndarray:
    """Vectorised ray casting."""

    lat = np.asarray(lat, dtype=float)
    lon = np.asarray(lon, dtype=float)
    inside = np.zeros(lat.shape, dtype=bool)
    n = len(polygon)
    j = n - 1
    for i in range(n):
        yi, xi = polygon[i]
        yj, xj = polygon[j]
        cond = (yi > lat) != (yj > lat)
        xcross = (xj - xi) * (lat - yi) / (yj - yi + 1e-18) + xi
        inside ^= cond & (lon < xcross)
        j = i
    return inside


def polygon_centroid(polygon: list[tuple[float, float]]) -> tuple[float, float]:
    lat = sum(p[0] for p in polygon) / len(polygon)
    lon = sum(p[1] for p in polygon) / len(polygon)
    return lat, lon


def circle_polygon(lat: float, lon: float, radius_nm: float, n: int = 24) -> list[tuple[float, float]]:
    return [destination(lat, lon, 360.0 * k / n, radius_nm * NM_M) for k in range(n)]
