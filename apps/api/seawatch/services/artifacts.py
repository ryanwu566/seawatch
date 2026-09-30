"""Read-only access to Phase 3B review-ranking artifacts.

This module locates and loads the local Phase 3B ranking Parquet outputs without
recalculating anything. It treats artifacts as immutable inputs: it only reads
them, never writes. It also defensively drops any vessel-identity columns so that
forbidden identifiers can never reach the API surface even if an upstream change
were to introduce them.
"""

from __future__ import annotations

from functools import lru_cache
import os
from pathlib import Path

import pandas as pd

# Identity fields that must never be exposed. Phase 3B already forbids these at
# write time; this is a defense-in-depth filter at read time.
FORBIDDEN_COLUMNS: frozenset[str] = frozenset(
    {"mmsi", "imo", "name", "callsign", "call_sign", "vessel_name", "shipname", "ship_name"}
)

# Local, gitignored Phase 3B row-level outputs, relative to the repository root.
_RANKING_DIR = Path("data/processed/review_ranking")
_RANKING_FILES: tuple[str, ...] = ("test_rankings.parquet", "calibration_rankings.parquet")

_ENV_ROOT = "SEAWATCH_DATA_ROOT"


class MissingArtifactError(RuntimeError):
    """Raised when a required Phase 3B ranking artifact is not available on disk."""


def _repo_root() -> Path:
    """Resolve the repository root that contains ``data/processed/review_ranking``.

    An override via the ``SEAWATCH_DATA_ROOT`` environment variable is honored so
    tests and alternative deployments can point at a fixture directory.
    """

    override = os.environ.get(_ENV_ROOT)
    if override:
        return Path(override)
    # apps/api/seawatch/services/artifacts.py -> repo root is four parents up.
    return Path(__file__).resolve().parents[4]


def ranking_artifact_paths() -> tuple[Path, ...]:
    """Return the candidate ranking artifact paths in priority order."""

    root = _repo_root()
    return tuple(root / _RANKING_DIR / name for name in _RANKING_FILES)


def _drop_forbidden(frame: pd.DataFrame) -> pd.DataFrame:
    forbidden = [name for name in frame.columns if str(name).casefold() in FORBIDDEN_COLUMNS]
    if forbidden:
        return frame.drop(columns=forbidden)
    return frame


def _load_uncached() -> pd.DataFrame:
    paths = ranking_artifact_paths()
    available = [path for path in paths if path.exists()]
    if not available:
        searched = ", ".join(str(path) for path in paths)
        raise MissingArtifactError(
            f"No Phase 3B ranking artifact found. Run the Phase 3B pipeline first. Searched: {searched}"
        )
    frames = []
    for path in available:
        # Read-only: pandas.read_parquet does not modify the source file.
        frame = _drop_forbidden(pd.read_parquet(path))
        frame["_artifact"] = path.name
        frames.append(frame)
    combined = pd.concat(frames, ignore_index=True) if len(frames) > 1 else frames[0]
    return combined


@lru_cache(maxsize=1)
def _cached_frame() -> pd.DataFrame:
    return _load_uncached()


def load_ranking_frame(*, use_cache: bool = True) -> pd.DataFrame:
    """Load the combined Phase 3B ranking frame (read-only).

    Args:
        use_cache: When True, reuse a process-level cached copy. Tests that swap
            the underlying artifacts should pass ``use_cache=False`` or call
            :func:`reset_cache`.

    Raises:
        MissingArtifactError: If no ranking artifact exists on disk.
    """

    frame = _cached_frame() if use_cache else _load_uncached()
    return frame.copy()


def reset_cache() -> None:
    """Clear the cached ranking frame (used by tests and after artifact refresh)."""

    _cached_frame.cache_clear()
