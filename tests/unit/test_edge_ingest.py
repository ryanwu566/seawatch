from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path

from apps.api.seawatch.live.config import LiveRuntimeConfig
from apps.api.seawatch.live.edge_ais import EdgeAisDecoder
from apps.api.seawatch.live.edge_ingest import EdgeAisConsumer
from apps.api.seawatch.live.resilience import EdgeInputKind
from apps.api.seawatch.live.store import LiveVesselStore


NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
FIXTURE = Path("tests/fixtures/ais/edge_nmea.txt")


def _lines() -> dict[str, bytes]:
    return dict(
        line.split(b"|", 1)
        for line in FIXTURE.read_bytes().splitlines()
        if line and not line.startswith(b"#")
    )


def _consumer(monkeypatch, env: dict[str, str] | None = None):
    monkeypatch.setattr("apps.api.seawatch.live.edge_ingest.utcnow", lambda: NOW)
    monkeypatch.setattr("apps.api.seawatch.live.store.utcnow", lambda: NOW)
    store = LiveVesselStore()
    consumer = EdgeAisConsumer(
        EdgeAisDecoder(),
        store,
        LiveRuntimeConfig.from_env(env or {}),
        monotonic=lambda: 50.0,
    )
    return consumer, store


def test_datagram_framing_updates_independent_store_health_and_track(monkeypatch) -> None:
    consumer, store = _consumer(monkeypatch)
    lines = _lines()

    consumer.handle_datagram(
        lines[b"class_a"] + b"\r\n\r\n" + lines[b"class_b"] + b"\n",
        ("127.0.0.1", 4000),
    )
    consumer.handle_datagram(lines[b"class_a_moved"], ("127.0.0.1", 4000))

    assert store.vessel_count() == 2
    assert len(store.get_trajectory("edge:416000001") or []) == 2
    assert consumer.health.received_messages == 3
    assert consumer.health.decoded_messages == 3
    assert consumer.health.rejected_messages == 0
    assert consumer.health.last_nmea_at == NOW
    assert consumer.health.last_valid_ais_at == NOW
    assert consumer.health.receiver_detected is True
    assert consumer.last_valid_monotonic == 50.0


def test_invalid_only_nonloopback_and_oversized_input_never_refresh_valid_time(
    monkeypatch,
) -> None:
    consumer, store = _consumer(monkeypatch)
    invalid = _lines()[b"class_a"][:-2] + b"00"

    consumer.handle_datagram(invalid, ("127.0.0.1", 4000))
    consumer.handle_datagram(_lines()[b"class_a"], ("192.0.2.10", 4000))
    consumer.handle_datagram(b"!" + b"X" * 2048, ("127.0.0.1", 4000))

    assert store.vessel_count() == 0
    assert consumer.health.received_messages == 3
    assert consumer.health.decoded_messages == 0
    assert consumer.health.rejected_messages == 3
    assert consumer.health.last_nmea_at == NOW
    assert consumer.health.last_valid_ais_at is None
    assert consumer.health.receiver_detected is False
    assert len(consumer.health.last_error or "") <= 240


def test_health_snapshot_distinguishes_listener_from_receiver_detection(monkeypatch) -> None:
    consumer, store = _consumer(monkeypatch)
    consumer.health.receiver_active = True
    consumer.health.input_kind = EdgeInputKind.UDP

    snapshot = consumer.health.snapshot(store, NOW)

    assert snapshot["receiver_active"] is True
    assert snapshot["receiver_detected"] is False
    assert snapshot["input_kind"] == "udp"
    assert snapshot["bind_host"] == "127.0.0.1"
    assert snapshot["bind_port"] == 10110
    assert snapshot["last_valid_ais_at"] is None
    assert snapshot["local_vessel_count"] == 0


def test_udp_bind_failure_is_recorded_once_without_retry(monkeypatch) -> None:
    consumer, _ = _consumer(monkeypatch, {"SEAWATCH_EDGE_INGEST": "true"})

    class FailingLoop:
        calls = 0

        async def create_datagram_endpoint(self, *args, **kwargs):
            self.calls += 1
            raise OSError("address unavailable")

    loop = FailingLoop()
    monkeypatch.setattr(asyncio, "get_running_loop", lambda: loop)

    asyncio.run(consumer._run_udp())

    assert loop.calls == 1
    assert consumer.health.receiver_active is False
    assert consumer.health.receiver_detected is False
    assert consumer.health.last_error == "OSError: address unavailable"


def test_explicit_replay_uses_decoder_store_and_replay_attribution(
    monkeypatch, tmp_path
) -> None:
    replay_file = tmp_path / "replay.nmea"
    replay_file.write_bytes(_lines()[b"class_a"] + b"\n")
    config = LiveRuntimeConfig.from_env(
        {
            "SEAWATCH_EDGE_INGEST": "true",
            "SEAWATCH_EDGE_REPLAY_ENABLED": "true",
            "SEAWATCH_EDGE_REPLAY_FILE": str(replay_file),
            "SEAWATCH_EDGE_REPLAY_INTERVAL_SECONDS": "0.001",
        }
    )
    monkeypatch.setattr("apps.api.seawatch.live.edge_ingest.utcnow", lambda: NOW)
    store = LiveVesselStore()

    async def scenario() -> EdgeAisConsumer:
        consumer = EdgeAisConsumer(EdgeAisDecoder(), store, config)
        consumer.start()
        for _ in range(100):
            if store.vessel_count():
                break
            await asyncio.sleep(0.001)
        await consumer.stop()
        return consumer

    consumer = asyncio.run(scenario())
    observation = store.snapshot()[0]

    assert consumer.health.input_kind is EdgeInputKind.REPLAY
    assert consumer.health.decoded_messages >= 1
    assert observation.source == "edge_replay"
    assert observation.synthesized is False


def test_replay_path_without_enable_flag_starts_no_input(monkeypatch, tmp_path) -> None:
    replay_file = tmp_path / "replay.nmea"
    replay_file.write_bytes(_lines()[b"class_a"])
    consumer, _ = _consumer(
        monkeypatch, {"SEAWATCH_EDGE_REPLAY_FILE": str(replay_file)}
    )

    consumer.start()

    assert consumer.health.receiver_active is False
    assert consumer.health.input_kind is EdgeInputKind.DISABLED
