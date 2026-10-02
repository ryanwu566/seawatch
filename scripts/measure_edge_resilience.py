"""Measure fixture decode/store/API costs without live hardware or Internet."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import statistics
import sys
import time
from typing import Iterable

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from apps.api.seawatch.live.edge_ais import EdgeAisDecoder
from apps.api.seawatch.live.runtime import get_live_runtime, reset_live_runtime
from apps.api.seawatch.live.schema import LiveVesselObservation
from apps.api.seawatch.live.store import LiveVesselStore
from apps.api.seawatch.main import create_app


def percentile(samples: Iterable[float], value: float) -> float:
    ordered = sorted(sample for sample in samples if math.isfinite(sample))
    if not ordered:
        raise ValueError("percentile requires at least one finite sample")
    rank = max(1, math.ceil((value / 100.0) * len(ordered)))
    return ordered[min(rank - 1, len(ordered) - 1)]


def _summary(samples: list[float]) -> dict[str, float]:
    return {
        "median": statistics.median(samples),
        "p95": percentile(samples, 95),
        "max": max(samples),
    }


def _fixture_lines(path: Path) -> list[bytes]:
    lines: list[bytes] = []
    for raw in path.read_bytes().splitlines():
        if not raw or raw.startswith(b"#"):
            continue
        lines.append(raw.split(b"|", 1)[1] if b"|" in raw else raw)
    return lines


def _decode(lines: list[bytes]) -> list[LiveVesselObservation]:
    decoder = EdgeAisDecoder()
    received_at = datetime(2026, 10, 1, tzinfo=timezone.utc)
    observations: list[LiveVesselObservation] = []
    for line in lines:
        observations.extend(decoder.feed_line(line, received_at=received_at).observations)
    return observations


def measure_fixture(path: Path, *, iterations: int) -> dict[str, object]:
    if iterations <= 0:
        raise ValueError("iterations must be positive")
    if not path.is_file():
        raise ValueError(f"fixture not found: {path}")
    lines = _fixture_lines(path)
    warmup = _decode(lines)
    if not warmup:
        raise ValueError("zero valid observations decoded; refusing misleading output")

    decode_samples: list[float] = []
    store_samples: list[float] = []
    rate_samples: list[float] = []
    api_samples: list[float] = []

    reset_live_runtime()
    runtime = get_live_runtime()
    runtime.cloud.consumer.health.connected = True
    client = TestClient(create_app())
    try:
        for _ in range(iterations):
            started = time.perf_counter_ns()
            observations = _decode(lines)
            decoded_ns = time.perf_counter_ns() - started
            if not observations:
                raise ValueError("zero valid observations decoded; refusing misleading output")

            store = LiveVesselStore()
            started = time.perf_counter_ns()
            store.update_many(observations)
            stored_ns = time.perf_counter_ns() - started

            runtime.cloud.store.clear()
            runtime.cloud.store.update_many(observations)
            started = time.perf_counter_ns()
            response = client.get("/live/vessels")
            api_ns = time.perf_counter_ns() - started
            if response.status_code != 200:
                raise RuntimeError(f"/live/vessels returned {response.status_code}")

            decode_samples.append(float(decoded_ns))
            store_samples.append(float(stored_ns))
            api_samples.append(float(api_ns))
            rate_samples.append(
                len(observations) / max((decoded_ns + stored_ns) / 1_000_000_000, 1e-12)
            )
    finally:
        client.close()
        reset_live_runtime()

    result: dict[str, object] = {
        "schema_version": 1,
        "timer": "time.perf_counter_ns",
        "iterations": iterations,
        "warmup_iterations": 1,
        "sample_count": len(decode_samples),
        "fixture": {
            "path": path.as_posix(),
            "line_count": len(lines),
            "decoded_observations": len(warmup),
        },
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "machine": platform.machine(),
            "logical_cpu_count": os.cpu_count(),
            "packages": {
                "pyais": importlib.metadata.version("pyais"),
                "fastapi": importlib.metadata.version("fastapi"),
            },
        },
        "metrics": {
            "decode_ns": _summary(decode_samples),
            "store_update_ns": _summary(store_samples),
            "ingest_rate_observations_per_second": _summary(rate_samples),
            "live_vessels_ns": _summary(api_samples),
        },
    }
    serialized = json.dumps(result).lower()
    forbidden = [
        field
        for field in ("mmsi", "imo", "callsign", "provider_id", "edge:")
        if field in serialized
    ]
    result["privacy_scan"] = {"forbidden_fields_found": forbidden}
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", required=True, type=Path)
    parser.add_argument("--iterations", required=True, type=int)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = measure_fixture(args.fixture, iterations=args.iterations)
    except (ValueError, RuntimeError) as exc:
        parser.error(str(exc))
    args.output.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
