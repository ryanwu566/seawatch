from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

from scripts.measure_edge_resilience import measure_fixture, percentile


FIXTURE = Path("tests/fixtures/ais/edge_nmea.txt")
SCRIPT = Path("scripts/measure_edge_resilience.py")


def test_percentile_uses_nearest_rank_with_sorted_finite_samples() -> None:
    assert percentile([40, 10, 30, 20], 50) == 20
    assert percentile([40, 10, 30, 20], 95) == 40
    with pytest.raises(ValueError):
        percentile([], 95)


def test_measurement_excludes_warmup_and_reports_required_aggregates() -> None:
    result = measure_fixture(FIXTURE, iterations=3)

    assert result["iterations"] == 3
    assert result["warmup_iterations"] == 1
    assert result["sample_count"] == 3
    assert result["fixture"]["decoded_observations"] > 0
    for name in (
        "decode_ns",
        "store_update_ns",
        "ingest_rate_observations_per_second",
        "live_vessels_ns",
    ):
        assert set(result["metrics"][name]) == {"median", "p95", "max"}
        assert result["metrics"][name]["max"] >= result["metrics"][name]["median"] >= 0
    assert result["timer"] == "time.perf_counter_ns"
    assert result["environment"]["python"]
    assert result["environment"]["platform"]
    assert result["environment"]["packages"]["pyais"] == "3.2.3"
    assert result["privacy_scan"]["forbidden_fields_found"] == []
    serialized = json.dumps(result).lower()
    assert "mmsi" not in serialized
    assert "callsign" not in serialized


def test_cli_requires_fixture_iterations_and_writes_only_valid_results(tmp_path: Path) -> None:
    output = tmp_path / "measurement.json"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--fixture",
            str(FIXTURE),
            "--iterations",
            "2",
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert output.is_file()
    assert json.loads(output.read_text(encoding="utf-8"))["sample_count"] == 2


def test_zero_valid_observations_refuses_misleading_output(tmp_path: Path) -> None:
    fixture = tmp_path / "invalid.txt"
    fixture.write_text("invalid NMEA only\n", encoding="utf-8")
    output = tmp_path / "must-not-exist.json"

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--fixture",
            str(fixture),
            "--iterations",
            "1",
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )

    assert result.returncode != 0
    assert "zero valid observations" in result.stderr.lower()
    assert not output.exists()
