from __future__ import annotations

from datetime import date
import json
from pathlib import Path

import pytest


CATALOG_PATH = Path("config/noaa_ais_phase3a_dates.json")


def _valid_payload() -> dict[str, object]:
    return {
        "schema_version": "phase3a-source-catalog-v1",
        "entries": [
            {
                "date": "2024-01-01",
                "source_url": "https://ocmgeodatastor1.blob.core.windows.net/marinecadastre/ais2024/ais-2024-01-01.parquet",
                "raw_filename": "ais-2024-01-01.parquet",
                "split_role": "train",
            },
            {
                "date": "2024-01-02",
                "source_url": "https://ocmgeodatastor1.blob.core.windows.net/marinecadastre/ais2024/ais-2024-01-02.parquet",
                "raw_filename": "ais-2024-01-02.parquet",
                "split_role": "calibration",
            },
            {
                "date": "2024-01-03",
                "source_url": "https://ocmgeodatastor1.blob.core.windows.net/marinecadastre/ais2024/ais-2024-01-03.parquet",
                "raw_filename": "ais-2024-01-03.parquet",
                "split_role": "test",
            },
        ],
    }


def _write_payload(tmp_path: Path, payload: dict[str, object]) -> Path:
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_committed_catalog_has_exact_dates_urls_files_and_roles() -> None:
    from apps.api.seawatch.datasets.source_catalog import load_phase3a_catalog

    catalog = load_phase3a_catalog(CATALOG_PATH)

    assert catalog.schema_version == "phase3a-source-catalog-v1"
    assert [entry.date.isoformat() for entry in catalog.entries] == [
        "2024-01-01",
        "2024-01-02",
        "2024-01-03",
    ]
    assert [entry.split_role for entry in catalog.entries] == [
        "train",
        "calibration",
        "test",
    ]
    for entry in catalog.entries:
        expected_name = f"ais-{entry.date.isoformat()}.parquet"
        assert entry.raw_filename == expected_name
        assert entry.source_url.endswith(f"/ais2024/{expected_name}")
        assert catalog.for_date(entry.date) == entry

    with pytest.raises(ValueError, match="not approved"):
        catalog.for_date(date(2024, 1, 4))


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda p: p["entries"].append({**p["entries"][-1], "date": "2024-01-04", "raw_filename": "ais-2024-01-04.parquet", "source_url": "https://ocmgeodatastor1.blob.core.windows.net/marinecadastre/ais2024/ais-2024-01-04.parquet"}), "exactly"),
        (lambda p: p["entries"].__setitem__(1, dict(p["entries"][0])), "duplicate"),
        (lambda p: p["entries"][1].__setitem__("split_role", "train"), "roles"),
        (lambda p: p["entries"][1].pop("split_role"), "missing"),
        (lambda p: p["entries"][1].__setitem__("source_url", "https://ocmgeodatastor1.blob.core.windows.net/marinecadastre/ais2024/ais-2024-01-03.parquet"), "date"),
        (lambda p: p.__setitem__("unexpected", True), "unknown"),
        (lambda p: p["entries"][1].__setitem__("source_url", "http://example.test/ais-2024-01-02.parquet"), "HTTPS"),
        (lambda p: p.__setitem__("schema_version", "wrong"), "schema_version"),
    ],
)
def test_catalog_rejects_invalid_or_expanded_scope(
    tmp_path: Path, mutation, message: str
) -> None:
    from apps.api.seawatch.datasets.source_catalog import load_phase3a_catalog

    payload = _valid_payload()
    mutation(payload)

    with pytest.raises(ValueError, match=message):
        load_phase3a_catalog(_write_payload(tmp_path, payload))
