"""Read-only access to the optional compact Historical Runtime v2 bundle."""

from __future__ import annotations

import json
import math
import os
from collections.abc import Mapping
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from threading import Lock
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

_PUBLIC_SUMMARY_FIELDS = frozenset(
    {
        "available",
        "runtime",
        "data_model",
        "date_range",
        "row_count",
        "unique_vessel_count",
        "traffic_cell_count",
        "dataset_hour_buckets",
        "mmsi_join_status_counts",
    }
)
_DATE_RANGE_KEYSETS = (
    frozenset({"start", "end"}),
    frozenset({"startUtc", "endUtc"}),
)
_DATA_MODELS = frozenset(
    {
        "standardized_hourly_vessel_presence",
        "standardized hourly vessel presence; not raw/message-level AIS",
    }
)
_MMSI_JOIN_STATUSES = frozenset(
    {"unique_9digit_candidate", "shared_9digit", "non_9digit", "missing"}
)
_PUBLIC_TRAFFIC_FIELDS = (
    "cell_lat",
    "cell_lon",
    "observation_count",
    "unique_vessel_count",
    "observed_days",
    "active_hour_buckets",
    "cell_active_hour_fraction",
    "avg_vessels_per_active_hour",
)
_LOAD_LOCK = Lock()


def bundle_dir() -> Path | None:
    """Resolve the configured bundle without assuming a machine-local path."""

    explicit = os.environ.get("SEAWATCH_HISTORICAL_RUNTIME", "").strip()
    if explicit:
        return Path(explicit).expanduser().resolve()

    data_root = os.environ.get("SEAWATCH_DATA_ROOT", "").strip()
    if not data_root:
        return None

    return (
        Path(data_root)
        / "historical_2026"
        / "runtime"
        / BUNDLE_NAME
    ).expanduser().resolve()


def available() -> bool:
    """Return whether all compact runtime artifacts are present."""

    root = bundle_dir()
    return root is not None and root.is_dir() and all(
        (root / filename).is_file() for filename in REQUIRED_FILES
    )


def _clean(value: Any) -> Any:
    """Convert artifact values to JSON-safe built-in values."""

    if value is None:
        return None
    if isinstance(value, Mapping):
        return {str(key): _clean(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(item) for item in value]

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
            return _clean(value.item())
        except (AttributeError, ValueError):
            pass

    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _record(series: pd.Series) -> dict[str, Any]:
    return {str(key): _clean(value) for key, value in series.items()}


def _is_exact_nine_digit_mmsi(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 9
        and all("0" <= character <= "9" for character in value)
    )


@lru_cache(maxsize=1)
def _load_once() -> dict[str, Any]:
    root = bundle_dir()
    if root is None:
        raise FileNotFoundError("Historical Runtime is not configured")

    missing = [
        filename for filename in REQUIRED_FILES if not (root / filename).is_file()
    ]
    if missing:
        raise FileNotFoundError("Historical Runtime bundle is incomplete")

    baselines = pd.read_parquet(root / "historical_baselines.parquet")
    habits = pd.read_parquet(root / "vessel_habits.parquet")
    traffic = pd.read_parquet(root / "traffic_context.parquet")
    context = joblib.load(root / "detection_context.joblib")
    metadata = json.loads(
        (root / "source_metadata.json").read_text(encoding="utf-8")
    )
    quality = json.loads(
        (root / "data_quality_report.json").read_text(encoding="utf-8")
    )

    safe = baselines[
        (baselines["mmsi_join_status"] == "unique_9digit_candidate")
        & baselines["mmsi"].map(_is_exact_nine_digit_mmsi)
    ].copy()
    if safe["mmsi"].duplicated().any():
        raise RuntimeError(
            "Historical Runtime identity invariant failed: "
            "unique_9digit_candidate MMSI is not one-to-one"
        )

    return {
        "baselines": baselines,
        "habits": habits,
        "traffic": traffic,
        "context": context,
        "metadata": metadata,
        "quality": quality,
        "baseline_by_mmsi": safe.set_index("mmsi", drop=False),
        "traffic_by_cell": traffic.set_index(
            ["cell_lat", "cell_lon"], drop=False
        ),
    }


def _load() -> dict[str, Any]:
    """Return one shared load, including when first requests are concurrent."""

    with _LOAD_LOCK:
        return _load_once()


def clear_cache() -> None:
    """Clear loaded artifacts so an intentional refresh can be observed."""

    with _LOAD_LOCK:
        _load_once.cache_clear()


def _nonnegative_int(value: Any, field: str) -> int:
    cleaned = _clean(value)
    if type(cleaned) is not int or cleaned < 0:
        raise ValueError(f"Historical Runtime {field} must be a nonnegative integer")
    return cleaned


def _finite_number(
    value: Any,
    field: str,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    cleaned = _clean(value)
    if type(cleaned) not in (int, float) or not math.isfinite(cleaned):
        raise ValueError(f"Historical Runtime {field} must be a finite number")
    number = float(cleaned)
    if minimum is not None and number < minimum:
        raise ValueError(f"Historical Runtime {field} is below its minimum")
    if maximum is not None and number > maximum:
        raise ValueError(f"Historical Runtime {field} exceeds its maximum")
    return number


def _coarse_coordinate(value: Any, field: str, limit: float) -> float:
    number = _finite_number(value, field, minimum=-limit, maximum=limit)
    rounded = round(number, 1)
    if not math.isclose(number, rounded, abs_tol=1e-9):
        raise ValueError(
            f"Historical Runtime {field} must remain on the 0.1-degree grid"
        )
    return rounded


def _iso_date_range(value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise ValueError("Historical Runtime date range must be an object")
    keys = frozenset(value.keys())
    if keys not in _DATE_RANGE_KEYSETS:
        raise ValueError("Historical Runtime date range has unexpected fields")

    result: dict[str, str] = {}
    for key in value:
        item = value[key]
        if not isinstance(item, str) or item.strip() != item or not item:
            raise ValueError("Historical Runtime date range must contain ISO dates")
        normalized = f"{item[:-1]}+00:00" if item.endswith("Z") else item
        try:
            datetime.fromisoformat(normalized)
        except ValueError as exc:
            raise ValueError(
                "Historical Runtime date range must contain ISO dates"
            ) from exc
        result[key] = item
    return result


def validate_summary(value: Any) -> dict[str, Any]:
    """Validate and rebuild the complete public response schema."""

    if not isinstance(value, Mapping) or frozenset(value.keys()) != _PUBLIC_SUMMARY_FIELDS:
        raise ValueError("Historical Runtime summary has unexpected fields")
    if value.get("available") is not True or value.get("runtime") != BUNDLE_NAME:
        raise ValueError("Historical Runtime summary identity is invalid")
    data_model = value.get("data_model")
    if data_model not in _DATA_MODELS:
        raise ValueError("Historical Runtime data model is invalid")

    raw_status_counts = value.get("mmsi_join_status_counts")
    if not isinstance(raw_status_counts, Mapping) or not raw_status_counts:
        raise ValueError("Historical Runtime join counts must be an object")
    if not set(raw_status_counts).issubset(_MMSI_JOIN_STATUSES):
        raise ValueError("Historical Runtime join counts have unexpected fields")
    status_counts = {
        status: _nonnegative_int(count, f"{status} count")
        for status, count in raw_status_counts.items()
    }

    return {
        "available": True,
        "runtime": BUNDLE_NAME,
        "data_model": data_model,
        "date_range": _iso_date_range(value.get("date_range")),
        "row_count": _nonnegative_int(value.get("row_count"), "row count"),
        "unique_vessel_count": _nonnegative_int(
            value.get("unique_vessel_count"), "unique vessel count"
        ),
        "traffic_cell_count": _nonnegative_int(
            value.get("traffic_cell_count"), "traffic cell count"
        ),
        "dataset_hour_buckets": _nonnegative_int(
            value.get("dataset_hour_buckets"), "dataset hour buckets"
        ),
        "mmsi_join_status_counts": status_counts,
    }


def summary() -> dict[str, Any]:
    """Return the strict aggregate public allowlist for Runtime v2."""

    data = _load()
    metadata = data["metadata"]
    context = data["context"]
    return validate_summary({
        "available": True,
        "runtime": BUNDLE_NAME,
        "data_model": metadata.get("dataModel"),
        "date_range": metadata.get("dateRange"),
        "row_count": metadata.get("rowCount"),
        "unique_vessel_count": metadata.get("uniqueVesselIdCount"),
        "traffic_cell_count": context["spatial_context"]["traffic_cell_count"],
        "dataset_hour_buckets": context["coverage_context"][
            "dataset_hour_buckets"
        ],
        "mmsi_join_status_counts": (
            context["identity_policy"]["mmsi_join_status_counts"]
        ),
    })


def traffic_cells() -> list[dict[str, int | float]]:
    """Return a strict aggregate allowlist for coarse traffic cells."""

    traffic = _load()["traffic"]
    missing = set(_PUBLIC_TRAFFIC_FIELDS).difference(traffic.columns)
    if missing:
        raise ValueError("Historical Runtime traffic schema is incomplete")

    cells: list[dict[str, int | float]] = []
    for _index, row in traffic.iterrows():
        cells.append({
            "cell_lat": _coarse_coordinate(row["cell_lat"], "cell latitude", 90),
            "cell_lon": _coarse_coordinate(row["cell_lon"], "cell longitude", 180),
            "observation_count": _nonnegative_int(
                row["observation_count"], "observation count"
            ),
            "unique_vessel_count": _nonnegative_int(
                row["unique_vessel_count"], "unique vessel count"
            ),
            "observed_days": _nonnegative_int(
                row["observed_days"], "observed days"
            ),
            "active_hour_buckets": _nonnegative_int(
                row["active_hour_buckets"], "active hour buckets"
            ),
            "cell_active_hour_fraction": _finite_number(
                row["cell_active_hour_fraction"],
                "cell active hour fraction",
                minimum=0,
                maximum=1,
            ),
            "avg_vessels_per_active_hour": _finite_number(
                row["avg_vessels_per_active_hour"],
                "average vessels per active hour",
                minimum=0,
            ),
        })
    return cells


def lookup_mmsi(mmsi: str) -> dict[str, Any] | None:
    """Return an internal record only for an exact conservative join key."""

    if not _is_exact_nine_digit_mmsi(mmsi):
        return None

    table = _load()["baseline_by_mmsi"]
    if mmsi not in table.index:
        return None

    row = table.loc[mmsi]
    if isinstance(row, pd.DataFrame):
        raise RuntimeError(
            "Historical Runtime identity invariant failed: MMSI is not one-to-one"
        )
    record = _record(row)
    record["join_policy"] = (
        "conservative_dataset_internal_one_to_one_candidate"
    )
    return record


def traffic_at(lat: float, lon: float) -> dict[str, Any] | None:
    """Return internal coarse 0.1-degree historical traffic context."""

    key = (round(float(lat), 1), round(float(lon), 1))
    table = _load()["traffic_by_cell"]
    if key not in table.index:
        return None

    row = table.loc[key]
    if isinstance(row, pd.DataFrame):
        row = row.iloc[0]
    record = _record(row)
    record["context_warning"] = (
        "Coarse GFW hourly presence cell; not raw AIS or a precise vessel position."
    )
    return record


def context_bundle() -> dict[str, Any]:
    """Return compact backend-only detection context."""

    return _load()["context"]
