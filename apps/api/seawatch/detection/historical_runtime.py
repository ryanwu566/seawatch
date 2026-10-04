"""Read-only adapter for the compact SeaWatch Historical Runtime bundle.

This adapter intentionally keeps GFW hourly presence separate from live/message-
level AIS. It exposes conservative vessel joins and coarse traffic context
without rebuilding Track objects from 33M historical observations.
"""

from __future__ import annotations

import json
import math
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import joblib
import pandas as pd


BUNDLE_NAME = "SeaWatch_Runtime_Taiwan_2026_v2"

REQUIRED_FILES = (
    "detection_context.joblib",
    "vessel_habits.parquet",
    "historical_baselines.parquet",
    "traffic_context.parquet",
    "source_metadata.json",
    "data_quality_report.json",
)


def bundle_dir() -> Path:
    """Resolve the compact historical runtime directory.

    Preferred:
        SEAWATCH_HISTORICAL_RUNTIME=/path/to/SeaWatch_Runtime_Taiwan_2026_v2

    Fallback:
        SEAWATCH_DATA_ROOT/historical_2026/runtime/SeaWatch_Runtime_Taiwan_2026_v2
    """

    explicit = os.environ.get("SEAWATCH_HISTORICAL_RUNTIME")

    if explicit:
        return Path(explicit).expanduser().resolve()

    root = Path(
        os.environ.get(
            "SEAWATCH_DATA_ROOT",
            "D:/SeaWatch",
        )
    )

    return (
        root
        / "historical_2026"
        / "runtime"
        / BUNDLE_NAME
    ).resolve()


def available() -> bool:
    root = bundle_dir()

    return root.is_dir() and all(
        (root / name).is_file()
        for name in REQUIRED_FILES
    )


def _clean(value: Any) -> Any:
    """Convert pandas/numpy scalar values into API-safe Python values."""

    if value is None:
        return None

    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass

    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except (TypeError, ValueError):
            pass

    if hasattr(value, "item"):
        try:
            return value.item()
        except (ValueError, AttributeError):
            pass

    if isinstance(value, float) and not math.isfinite(value):
        return None

    return value


def _record(series: pd.Series) -> dict[str, Any]:
    return {
        str(key): _clean(value)
        for key, value in series.items()
    }


@lru_cache(maxsize=1)
def _load() -> dict[str, Any]:
    root = bundle_dir()

    missing = [
        name
        for name in REQUIRED_FILES
        if not (root / name).is_file()
    ]

    if missing:
        raise FileNotFoundError(
            f"Historical Runtime bundle incomplete at {root}: {missing}"
        )

    baselines = pd.read_parquet(
        root / "historical_baselines.parquet"
    )

    habits = pd.read_parquet(
        root / "vessel_habits.parquet"
    )

    traffic = pd.read_parquet(
        root / "traffic_context.parquet"
    )

    context = joblib.load(
        root / "detection_context.joblib"
    )

    metadata = json.loads(
        (root / "source_metadata.json").read_text(
            encoding="utf-8"
        )
    )

    quality = json.loads(
        (root / "data_quality_report.json").read_text(
            encoding="utf-8"
        )
    )

    safe = baselines[
        baselines["mmsi_join_status"]
        == "unique_9digit_candidate"
    ].copy()

    if safe["mmsi"].duplicated().any():
        raise RuntimeError(
            "Historical Runtime identity invariant failed: "
            "unique_9digit_candidate MMSI is not one-to-one"
        )

    baseline_by_mmsi = safe.set_index(
        "mmsi",
        drop=False,
    )

    baseline_by_vessel = baselines.set_index(
        "vesselId",
        drop=False,
    )

    habits_by_vessel = habits.set_index(
        "vesselId",
        drop=False,
    )

    traffic_by_cell = traffic.set_index(
        ["cell_lat", "cell_lon"],
        drop=False,
    )

    return {
        "root": root,
        "baselines": baselines,
        "habits": habits,
        "traffic": traffic,
        "context": context,
        "metadata": metadata,
        "quality": quality,
        "baseline_by_mmsi": baseline_by_mmsi,
        "baseline_by_vessel": baseline_by_vessel,
        "habits_by_vessel": habits_by_vessel,
        "traffic_by_cell": traffic_by_cell,
    }


def clear_cache() -> None:
    """Reload the bundle after historical artifacts are refreshed."""

    _load.cache_clear()


def summary() -> dict[str, Any]:
    data = _load()

    return {
        "available": True,
        "runtime": BUNDLE_NAME,
        "data_model": data["metadata"].get("dataModel"),
        "date_range": data["metadata"].get("dateRange"),
        "row_count": data["metadata"].get("rowCount"),
        "unique_vessel_count": data["metadata"].get(
            "uniqueVesselIdCount"
        ),
        "traffic_cell_count": data["context"][
            "spatial_context"
        ]["traffic_cell_count"],
        "dataset_hour_buckets": data["context"][
            "coverage_context"
        ]["dataset_hour_buckets"],
        "mmsi_join_status_counts": data["context"][
            "identity_policy"
        ]["mmsi_join_status_counts"],
    }


def lookup_mmsi(mmsi: str) -> dict[str, Any] | None:
    """Conservative cross-source lookup for a live AIS MMSI.

    Returns a baseline only when the Runtime classified the MMSI as
    unique_9digit_candidate. Shared, malformed, or missing MMSIs are not joined.
    """

    key = str(mmsi).strip()

    if not (
        len(key) == 9
        and key.isdigit()
    ):
        return None

    data = _load()
    table = data["baseline_by_mmsi"]

    if key not in table.index:
        return None

    row = table.loc[key]

    if isinstance(row, pd.DataFrame):
        raise RuntimeError(
            f"Historical Runtime identity invariant failed for MMSI {key}"
        )

    out = _record(row)
    out["join_policy"] = (
        "conservative_dataset_internal_one_to_one_candidate"
    )

    return out


def lookup_vessel_id(
    vessel_id: str,
) -> dict[str, Any] | None:
    """Internal GFW-only lookup by opaque historical vesselId."""

    key = str(vessel_id).strip()
    data = _load()
    table = data["baseline_by_vessel"]

    if key not in table.index:
        return None

    return _record(table.loc[key])


def vessel_habit(
    vessel_id: str,
) -> dict[str, Any] | None:
    """Return evidence-aware GFW historical presence habit."""

    key = str(vessel_id).strip()
    data = _load()
    table = data["habits_by_vessel"]

    if key not in table.index:
        return None

    return _record(table.loc[key])


def traffic_at(
    lat: float,
    lon: float,
) -> dict[str, Any] | None:
    """Return coarse 0.1-degree historical traffic context."""

    cell_lat = round(float(lat), 1)
    cell_lon = round(float(lon), 1)

    data = _load()
    table = data["traffic_by_cell"]

    key = (cell_lat, cell_lon)

    if key not in table.index:
        return None

    row = table.loc[key]

    if isinstance(row, pd.DataFrame):
        row = row.iloc[0]

    out = _record(row)

    out["context_warning"] = (
        "Coarse GFW hourly presence cell; "
        "not raw AIS or a precise vessel position."
    )

    return out


def context_bundle() -> dict[str, Any]:
    """Read-only compact context for backend detection/intelligence code."""

    return _load()["context"]
