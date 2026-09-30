"""Read-only access to privacy-safe trajectory geometry.

This service builds a GeoJSON LineString for a track from the existing Phase 1
processed observation artifacts. It reads only ``track_id`` and coordinates; it
recalculates no trajectories and exposes no vessel identifiers.
"""

from __future__ import annotations

from functools import lru_cache
import glob
import os
from pathlib import Path

import pandas as pd

# Identity fields that must never be exposed. Phase 1 artifacts already forbid
# these; this is a defense-in-depth guard at read time.
FORBIDDEN_COLUMNS: frozenset[str] = frozenset(
    {"mmsi", "imo", "name", "callsign", "call_sign", "vessel_name", "shipname", "ship_name"}
)

# Local, gitignored Phase 1 processed observation artifacts, relative to the
# repository root. These contain track_id + coordinates and no identifiers.
_OBSERVATION_GLOB = "data/processed/noaa_ais_*_sf_bay.parquet"
_GEOMETRY_COLUMNS = ("track_id", "base_date_time", "longitude", "latitude")

_ENV_ROOT = "SEAWATCH_DATA_ROOT"


class MissingArtifactError(RuntimeError):
    """Raised when no Phase 1 observation artifact is available on disk."""


def _repo_root() -> Path:
    override = os.environ.get(_ENV_ROOT)
    if override:
        return Path(override)
    # apps/api/seawatch/services/geometry_service.py -> repo root is four parents up.
    return Path(__file__).resolve().parents[4]


def observation_artifact_paths() -> tuple[Path, ...]:
    """Return the Phase 1 observation artifact paths, sorted for determinism."""

    root = _repo_root()
    matches = sorted(glob.glob(str(root / _OBSERVATION_GLOB)))
    return tuple(Path(match) for match in matches)


def _drop_forbidden(frame: pd.DataFrame) -> pd.DataFrame:
    forbidden = [name for name in frame.columns if str(name).casefold() in FORBIDDEN_COLUMNS]
    if forbidden:
        return frame.drop(columns=forbidden)
    return frame


def _load_uncached() -> pd.DataFrame:
    paths = observation_artifact_paths()
    if not paths:
        raise MissingArtifactError(
            "No Phase 1 observation artifact found. Run the Phase 1 pipeline first. "
            f"Searched: {_repo_root() / _OBSERVATION_GLOB}"
        )
    frames = []
    for path in paths:
        # Read-only: only the columns needed for geometry are loaded.
        frame = pd.read_parquet(path, columns=list(_GEOMETRY_COLUMNS))
        frame = _drop_forbidden(frame)
        frames.append(frame)
    return pd.concat(frames, ignore_index=True) if len(frames) > 1 else frames[0]


@lru_cache(maxsize=1)
def _cached_frame() -> pd.DataFrame:
    return _load_uncached()


def reset_cache() -> None:
    """Clear the cached observation frame (used by tests and after refresh)."""

    _cached_frame.cache_clear()


def get_track_line_coordinates(
    track_id: str, *, use_cache: bool = True
) -> list[list[float]] | None:
    """Return ordered [lon, lat] coordinates for a track, or None if unavailable.

    Coordinates are ordered by observation time. A track needs at least two valid
    coordinate pairs to form a LineString; otherwise None is returned.

    Raises:
        MissingArtifactError: If no Phase 1 observation artifact exists.
    """

    frame = _cached_frame() if use_cache else _load_uncached()
    subset = frame.loc[frame["track_id"].astype("string") == str(track_id)]
    if subset.empty:
        return None

    subset = subset.copy()
    subset["base_date_time"] = pd.to_datetime(
        subset["base_date_time"], errors="coerce", utc=True
    )
    longitude = pd.to_numeric(subset["longitude"], errors="coerce")
    latitude = pd.to_numeric(subset["latitude"], errors="coerce")
    valid = (
        longitude.between(-180.0, 180.0)
        & latitude.between(-90.0, 90.0)
        & longitude.notna()
        & latitude.notna()
    )
    subset = subset.assign(longitude=longitude, latitude=latitude).loc[valid]
    subset = subset.sort_values("base_date_time", kind="mergesort")

    coordinates = [
        [float(lon), float(lat)]
        for lon, lat in zip(subset["longitude"], subset["latitude"])
    ]
    if len(coordinates) < 2:
        return None
    return coordinates
