from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from typing import Any, Callable

import joblib
import numpy as np
import pandas as pd
import pytest

from apps.api.seawatch.detection import historical_runtime


REQUIRED_ARTIFACTS = (
    "detection_context.joblib",
    "vessel_habits.parquet",
    "historical_baselines.parquet",
    "traffic_context.parquet",
    "source_metadata.json",
    "data_quality_report.json",
)


def _make_bundle(path: Path) -> Path:
    path.mkdir(parents=True)
    for filename in REQUIRED_ARTIFACTS:
        (path / filename).touch()
    return path


def _write_compact_bundle(path: Path) -> Path:
    path.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "vesselId": "gfw-vessel-sensitive-001",
                "mmsi": "123456789",
                "mmsi_join_status": "unique_9digit_candidate",
                "presence_hours": np.int64(41),
            },
            {
                "vesselId": "gfw-vessel-shared-002",
                "mmsi": "987654321",
                "mmsi_join_status": "shared_9digit",
                "presence_hours": np.int64(17),
            },
            {
                "vesselId": "gfw-vessel-invalid-003",
                "mmsi": "12345ABCD",
                "mmsi_join_status": "unique_9digit_candidate",
                "presence_hours": np.int64(5),
            },
            {
                "vesselId": "gfw-vessel-short-004",
                "mmsi": "12345678",
                "mmsi_join_status": "unique_9digit_candidate",
                "presence_hours": np.int64(3),
            },
            {
                "vesselId": "gfw-vessel-missing-005",
                "mmsi": None,
                "mmsi_join_status": "missing",
                "presence_hours": np.int64(1),
            },
        ]
    ).to_parquet(path / "historical_baselines.parquet", index=False)
    pd.DataFrame(
        [
            {
                "vesselId": "gfw-vessel-sensitive-001",
                "usual_presence_hours": np.int64(28),
            }
        ]
    ).to_parquet(path / "vessel_habits.parquet", index=False)
    pd.DataFrame(
        [
            {
                "cell_lat": 25.0,
                "cell_lon": 121.5,
                "historical_presence_observations": np.int64(1200),
            }
        ]
    ).to_parquet(path / "traffic_context.parquet", index=False)
    joblib.dump(
        {
            "spatial_context": {"traffic_cell_count": np.int64(2457)},
            "coverage_context": {"dataset_hour_buckets": np.int64(6528)},
            "identity_policy": {
                "mmsi_join_status_counts": {
                    "unique_9digit_candidate": np.int64(66043),
                    "shared_9digit": np.int64(12),
                    "non_9digit": np.int64(8),
                    "missing": np.int64(3),
                }
            },
            "local_path": "D:/private/runtime",
            "credential": "super-secret-token",
        },
        path / "detection_context.joblib",
    )
    (path / "source_metadata.json").write_text(
        json.dumps(
            {
                "dataModel": "standardized_hourly_vessel_presence",
                "dateRange": {"start": "2026-01-01", "end": "2026-09-29"},
                "rowCount": 33_200_000,
                "uniqueVesselIdCount": 400_800,
                "sourcePath": "D:/private/raw-presence.parquet",
                "sampleMmsi": "123456789",
                "sampleVesselId": "gfw-vessel-sensitive-001",
                "credential": "super-secret-token",
            }
        ),
        encoding="utf-8",
    )
    (path / "data_quality_report.json").write_text(
        json.dumps(
            {
                "rawDataset": "D:/private/raw-presence.parquet",
                "credential": "super-secret-token",
            }
        ),
        encoding="utf-8",
    )
    return path


@pytest.fixture(autouse=True)
def _reset_runtime_cache() -> Any:
    clear_cache = getattr(historical_runtime, "clear_cache", None)
    if clear_cache is not None:
        clear_cache()
    yield
    if clear_cache is not None:
        clear_cache()


@pytest.fixture
def compact_bundle(monkeypatch, tmp_path: Path) -> Path:
    bundle = _write_compact_bundle(tmp_path / "runtime")
    monkeypatch.setenv("SEAWATCH_HISTORICAL_RUNTIME", str(bundle))
    monkeypatch.delenv("SEAWATCH_DATA_ROOT", raising=False)
    return bundle


def _capture_compact_reads(
    monkeypatch,
) -> tuple[list[str], Callable[[], None]]:
    opened: list[str] = []
    original_read_parquet = pd.read_parquet
    original_joblib_load = joblib.load
    original_read_text = Path.read_text

    def read_parquet(path: Any, *args: Any, **kwargs: Any) -> pd.DataFrame:
        opened.append(Path(path).name)
        return original_read_parquet(path, *args, **kwargs)

    def load(path: Any, *args: Any, **kwargs: Any) -> Any:
        opened.append(Path(path).name)
        return original_joblib_load(path, *args, **kwargs)

    def read_text(path: Path, *args: Any, **kwargs: Any) -> str:
        opened.append(path.name)
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(pd, "read_parquet", read_parquet)
    monkeypatch.setattr(joblib, "load", load)
    monkeypatch.setattr(Path, "read_text", read_text)

    return opened, historical_runtime.clear_cache


def test_explicit_runtime_path_wins(monkeypatch, tmp_path: Path) -> None:
    explicit = _make_bundle(tmp_path / "explicit-runtime")
    monkeypatch.setenv("SEAWATCH_HISTORICAL_RUNTIME", str(explicit))
    monkeypatch.setenv("SEAWATCH_DATA_ROOT", str(tmp_path / "data-root"))

    assert historical_runtime.bundle_dir() == explicit
    assert historical_runtime.available() is True


def test_data_root_fallback_is_used(monkeypatch, tmp_path: Path) -> None:
    data_root = tmp_path / "data-root"
    expected = _make_bundle(
        data_root / "historical_2026" / "runtime" / "SeaWatch_Runtime_Taiwan_2026_v2"
    )
    monkeypatch.delenv("SEAWATCH_HISTORICAL_RUNTIME", raising=False)
    monkeypatch.setenv("SEAWATCH_DATA_ROOT", str(data_root))

    assert historical_runtime.bundle_dir() == expected
    assert historical_runtime.available() is True


def test_blank_explicit_path_uses_data_root(monkeypatch, tmp_path: Path) -> None:
    data_root = tmp_path / "data-root"
    expected = _make_bundle(
        data_root / "historical_2026" / "runtime" / "SeaWatch_Runtime_Taiwan_2026_v2"
    )
    monkeypatch.setenv("SEAWATCH_HISTORICAL_RUNTIME", "  \t ")
    monkeypatch.setenv("SEAWATCH_DATA_ROOT", str(data_root))

    assert historical_runtime.bundle_dir() == expected
    assert historical_runtime.available() is True


def test_missing_configuration_or_bundle_is_unavailable(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("SEAWATCH_HISTORICAL_RUNTIME", raising=False)
    monkeypatch.delenv("SEAWATCH_DATA_ROOT", raising=False)

    assert historical_runtime.bundle_dir() is None
    assert historical_runtime.available() is False

    missing = tmp_path / "missing-runtime"
    monkeypatch.setenv("SEAWATCH_HISTORICAL_RUNTIME", str(missing))

    assert historical_runtime.bundle_dir() == missing
    assert historical_runtime.available() is False


def test_valid_compact_bundle_returns_expected_summary(compact_bundle: Path) -> None:
    assert historical_runtime.summary() == {
        "available": True,
        "runtime": "SeaWatch_Runtime_Taiwan_2026_v2",
        "data_model": "standardized_hourly_vessel_presence",
        "date_range": {"start": "2026-01-01", "end": "2026-09-29"},
        "row_count": 33_200_000,
        "unique_vessel_count": 400_800,
        "traffic_cell_count": 2457,
        "dataset_hour_buckets": 6528,
        "mmsi_join_status_counts": {
            "unique_9digit_candidate": 66043,
            "shared_9digit": 12,
            "non_9digit": 8,
            "missing": 3,
        },
    }


def test_verified_runtime_metadata_shape_is_accepted(
    compact_bundle: Path,
) -> None:
    metadata_path = compact_bundle / "source_metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["dataModel"] = (
        "standardized hourly vessel presence; not raw/message-level AIS"
    )
    metadata["dateRange"] = {
        "startUtc": "2026-01-01T00:00:00+00:00",
        "endUtc": "2026-09-29T23:00:00+00:00",
    }
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    historical_runtime.clear_cache()

    result = historical_runtime.summary()

    assert result["data_model"] == (
        "standardized hourly vessel presence; not raw/message-level AIS"
    )
    assert result["date_range"] == metadata["dateRange"]


def test_summary_omits_paths_and_raw_identifiers(compact_bundle: Path) -> None:
    serialized = json.dumps(historical_runtime.summary())

    assert "D:/private" not in serialized
    assert "123456789" not in serialized
    assert "gfw-vessel-sensitive-001" not in serialized
    assert "super-secret-token" not in serialized
    assert set(historical_runtime.summary()) == {
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


def test_only_unique_nine_digit_candidates_are_indexed(compact_bundle: Path) -> None:
    record = historical_runtime.lookup_mmsi("123456789")

    assert record is not None
    assert record["vesselId"] == "gfw-vessel-sensitive-001"
    assert record["presence_hours"] == 41
    assert record["join_policy"] == (
        "conservative_dataset_internal_one_to_one_candidate"
    )


def test_shared_and_invalid_mmsi_are_rejected(compact_bundle: Path) -> None:
    assert historical_runtime.lookup_mmsi("987654321") is None
    assert historical_runtime.lookup_mmsi("12345ABCD") is None
    assert historical_runtime.lookup_mmsi("12345678") is None
    assert historical_runtime.lookup_mmsi(123456789) is None
    assert historical_runtime.lookup_mmsi(" 123456789 ") is None
    assert historical_runtime.lookup_mmsi("") is None


def test_duplicate_safe_candidate_mmsi_fails_invariant(
    monkeypatch, compact_bundle: Path
) -> None:
    baselines_path = compact_bundle / "historical_baselines.parquet"
    baselines = pd.read_parquet(baselines_path)
    duplicate = baselines.iloc[[0]].assign(vesselId="gfw-vessel-duplicate-006")
    pd.concat([baselines, duplicate], ignore_index=True).to_parquet(
        baselines_path, index=False
    )
    historical_runtime.clear_cache()

    with pytest.raises(RuntimeError, match="one-to-one"):
        historical_runtime.summary()


def test_traffic_lookup_rounds_to_coarse_tenth_degree_cell(
    compact_bundle: Path,
) -> None:
    record = historical_runtime.traffic_at(25.04, 121.46)

    assert record == {
        "cell_lat": 25.0,
        "cell_lon": 121.5,
        "historical_presence_observations": 1200,
        "context_warning": (
            "Coarse GFW hourly presence cell; not raw AIS or a precise vessel position."
        ),
    }
    assert historical_runtime.traffic_at(20.0, 120.0) is None


def test_loader_reads_only_compact_artifacts(
    monkeypatch, compact_bundle: Path
) -> None:
    (compact_bundle / "raw_presence_observations.parquet").touch()
    opened, _ = _capture_compact_reads(monkeypatch)

    historical_runtime.summary()

    assert set(opened) == set(REQUIRED_ARTIFACTS)
    assert "raw_presence_observations.parquet" not in opened


def test_loader_is_cached_across_summary_calls(
    monkeypatch, compact_bundle: Path
) -> None:
    opened, _ = _capture_compact_reads(monkeypatch)

    first = historical_runtime.summary()
    second = historical_runtime.summary()

    assert first == second
    assert len(opened) == len(REQUIRED_ARTIFACTS)


def test_concurrent_first_load_reads_compact_artifacts_once(
    monkeypatch, compact_bundle: Path
) -> None:
    opened, _ = _capture_compact_reads(monkeypatch)
    ready = Barrier(2)

    def read_summary() -> dict[str, Any]:
        ready.wait()
        return historical_runtime.summary()

    with ThreadPoolExecutor(max_workers=2) as executor:
        summaries = list(executor.map(lambda _index: read_summary(), range(2)))

    assert summaries[0] == summaries[1]
    assert len(opened) == len(REQUIRED_ARTIFACTS)
