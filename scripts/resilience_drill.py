"""Deterministic, simulation-only Cloud/Edge resilience policy drill."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from apps.api.seawatch.live.config import LiveRuntimeConfig
from apps.api.seawatch.live.edge_ais import EdgeAisDecoder
from apps.api.seawatch.live.resilience import (
    EdgeInputKind,
    OperatingMode,
    ResilienceModeManager,
    SourceHealthSnapshot,
)
from apps.api.seawatch.live.store import LiveVesselStore


DEFAULT_FIXTURE = Path("tests/fixtures/ais/edge_nmea.txt")


@dataclass
class Clock:
    value: float = 100.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def _source(
    name: str,
    last_message: float | None,
    *,
    count: int = 0,
    input_kind: EdgeInputKind | None = None,
) -> SourceHealthSnapshot:
    return SourceHealthSnapshot(
        source=name,
        connected=last_message is not None,
        last_message_at=None,
        last_message_monotonic=last_message,
        vessel_count=count,
        input_kind=input_kind,
    )


def _decode_fixture(path: Path, decoder: EdgeAisDecoder, store: LiveVesselStore) -> int:
    received_at = datetime(2026, 10, 1, tzinfo=timezone.utc)
    decoded = 0
    for raw_line in path.read_bytes().splitlines():
        if not raw_line or raw_line.startswith(b"#") or b"|" not in raw_line:
            continue
        result = decoder.feed_line(raw_line.split(b"|", 1)[1], received_at=received_at)
        decoded += len(result.observations)
        store.update_many(result.observations)
    return decoded


def run_drill(fixture: Path) -> list[dict[str, object]]:
    config = LiveRuntimeConfig.from_env()
    clock = Clock()
    manager = ResilienceModeManager(config, monotonic=clock)
    decoder = EdgeAisDecoder(monotonic=clock)
    edge_store = LiveVesselStore()
    records: list[dict[str, object]] = []

    def record(stage: str, mode: OperatingMode, **details: object) -> None:
        records.append(
            {
                "stage": stage,
                "label": f"SIMULATED {stage}",
                "simulated": True,
                "mode": mode.value,
                "recovery_seconds": config.cloud_recovery_seconds,
                **details,
            }
        )

    cloud_last = clock.value
    none_edge = _source("edge_ais", None, input_kind=EdgeInputKind.DISABLED)
    status = manager.evaluate(_source("cloud", cloud_last, count=1), none_edge)
    record("cloud_live", status.mode)

    clock.advance(config.cloud_stale_seconds + 1.0)
    status = manager.evaluate(_source("cloud", cloud_last, count=1), none_edge)
    record("cloud_outage", status.mode)

    decoded = _decode_fixture(fixture, decoder, edge_store)
    record(
        "explicit_replay",
        manager.current_mode,
        replay=True,
        decoded_observations=decoded,
        stored_vessels=edge_store.vessel_count(),
    )

    edge_last = clock.value
    replay_edge = _source(
        "edge_ais",
        edge_last,
        count=edge_store.vessel_count(),
        input_kind=EdgeInputKind.REPLAY,
    )
    status = manager.evaluate(_source("cloud", cloud_last, count=1), replay_edge)
    record("edge_replay", status.mode)

    clock.advance(1.0)
    cloud_last = clock.value
    edge_last = clock.value
    replay_edge = _source(
        "edge_ais",
        edge_last,
        count=edge_store.vessel_count(),
        input_kind=EdgeInputKind.REPLAY,
    )
    status = manager.evaluate(_source("cloud", cloud_last, count=1), replay_edge)
    record("cloud_restored_held", status.mode)

    clock.advance(config.cloud_recovery_seconds)
    record(
        "recovery_elapsed",
        manager.current_mode,
        elapsed_seconds=config.cloud_recovery_seconds,
    )

    status = manager.evaluate(
        _source("cloud", cloud_last, count=1),
        _source(
            "edge_ais",
            edge_last,
            count=edge_store.vessel_count(),
            input_kind=EdgeInputKind.REPLAY,
        ),
    )
    record("cloud_live_restored", status.mode)
    return records


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--enable-simulation", action="store_true")
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args(argv)
    if not args.enable_simulation:
        parser.error("refusing to run without --enable-simulation")
    if not args.fixture.is_file():
        parser.error(f"simulation fixture not found: {args.fixture}")

    records = run_drill(args.fixture)
    if args.json_output is not None:
        args.json_output.write_text(
            json.dumps(records, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    for record in records:
        print(json.dumps(record, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
