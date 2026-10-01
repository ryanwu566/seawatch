"""Phase 7A live proof + performance measurement.

Starts the real Open Waters ingest consumer against the Taiwan bbox, waits for
the in-memory store to populate, then measures:
- upstream message rate
- current vessel count
- GET /live/vessels response bytes and latency (served from the store)
- a sample track response

Writes results to .swtmp_live_proof.json. Live network required (run manually).
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

# Ensure the repository root is importable when run directly as a script.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from apps.api.seawatch import live as live_pkg


async def main() -> None:
    live_pkg.reset_live_state()
    store = live_pkg.get_store()
    consumer = live_pkg.get_consumer()
    consumer.start()

    # Let the snapshot + stream populate the store.
    warmup = 20
    t0 = time.monotonic()
    await asyncio.sleep(warmup)
    elapsed = time.monotonic() - t0

    msg_count = store.message_count()
    vessel_count = store.vessel_count()
    rate = msg_count / elapsed if elapsed else 0.0

    # Measure GET /live/vessels via the real app (served from the store).
    from fastapi.testclient import TestClient
    from apps.api.seawatch.main import create_app

    client = TestClient(create_app())

    lat_before = time.perf_counter()
    response = client.get("/live/vessels")
    latency_ms = (time.perf_counter() - lat_before) * 1000.0
    payload = response.json()
    payload_bytes = len(response.content)

    sample_track = None
    if payload["features"]:
        vid = payload["features"][0]["id"]
        track = client.get(f"/live/vessels/{vid}/track").json()
        sample_track = {
            "vessel_id": vid,
            "point_count": track["properties"]["point_count"],
        }

    health = consumer.health_snapshot()
    await consumer.stop()

    result = {
        "warmup_seconds": warmup,
        "upstream_messages": msg_count,
        "upstream_message_rate_per_sec": round(rate, 1),
        "current_vessel_count": vessel_count,
        "live_vessels_latency_ms": round(latency_ms, 2),
        "live_vessels_payload_bytes": payload_bytes,
        "live_vessels_payload_kb": round(payload_bytes / 1024, 1),
        "sample_track": sample_track,
        "health": health,
    }
    with open(".swtmp_live_proof.json", "w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
