"""Phase 7A smoke tests for FREE real-time Taiwan AIS providers.

This script performs *live* network checks against two providers and reports
whether real Taiwan vessel AIS positions actually arrive TODAY. It writes no
application code and makes no decisions on its own: it only measures and prints
evidence so a provider choice can be made from observed data.

Providers probed:

A. AISStream.io   wss://stream.aisstream.io/v0/stream   (requires AISSTREAM_API_KEY)
B. Open Waters    wss://ais.openwaters.io/v1/stream      (anonymous)
                  https://ais.openwaters.io/v1/vessels    (anonymous REST snapshot)

Taiwan bounding box tested (lat/lon):
    minLat 21.5  minLon 118.0  maxLat 26.5  maxLon 123.5

IMPORTANT: a successful WebSocket connection alone does NOT count as success.
Success requires real Taiwan position frames to arrive.

Usage:
    python scripts/smoke_test_live_ais.py            # both providers, 30s each
    python scripts/smoke_test_live_ais.py --seconds 30 --provider all

Credentials are read from the environment only and never printed.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import ssl
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

try:
    import websockets
except ImportError as exc:  # pragma: no cover - script-only guard
    raise SystemExit(
        "The 'websockets' package is required: pip install websockets"
    ) from exc

try:
    import httpx
except ImportError:  # pragma: no cover
    httpx = None  # REST snapshot test will be skipped


# Taiwan test bounding box (lat/lon corners).
MIN_LAT, MIN_LON, MAX_LAT, MAX_LON = 21.5, 118.0, 26.5, 123.5

AISSTREAM_URL = "wss://stream.aisstream.io/v0/stream"
OPENWATERS_WS_URL = "wss://ais.openwaters.io/v1/stream"
OPENWATERS_REST_URL = "https://ais.openwaters.io/v1/vessels"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _in_taiwan_bbox(lat: float | None, lon: float | None) -> bool:
    if lat is None or lon is None:
        return False
    return MIN_LAT <= lat <= MAX_LAT and MIN_LON <= lon <= MAX_LON


@dataclass
class SmokeResult:
    provider: str
    connected: bool = False
    subscription_confirmed: bool | None = None
    total_frames: int = 0
    position_frames: int = 0
    unique_vessels: int = 0
    taiwan_position_frames: int = 0
    unique_taiwan_vessels: int = 0
    latest_message_timestamps: list[str] = field(default_factory=list)
    sample_positions: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    notes: list[str] = field(default_factory=list)

    def usable(self) -> bool:
        """A provider is usable only if real Taiwan position frames arrived."""
        return self.connected and self.taiwan_position_frames > 0

    def summary(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "connected": self.connected,
            "subscription_confirmed": self.subscription_confirmed,
            "total_frames": self.total_frames,
            "position_frames": self.position_frames,
            "unique_vessels": self.unique_vessels,
            "taiwan_position_frames": self.taiwan_position_frames,
            "unique_taiwan_vessels": self.unique_taiwan_vessels,
            "latest_message_timestamps": self.latest_message_timestamps[-5:],
            "sample_positions": self.sample_positions[:3],
            "error": self.error,
            "notes": self.notes,
            "usable": self.usable(),
        }


# --------------------------------------------------------------------------- #
# A. AISStream.io
# --------------------------------------------------------------------------- #
async def smoke_aisstream(seconds: int) -> SmokeResult:
    result = SmokeResult(provider="aisstream")
    api_key = os.environ.get("AISSTREAM_API_KEY")
    if not api_key:
        result.error = "AISSTREAM_API_KEY not set; AISStream requires a free API key to receive any messages."
        result.notes.append("Skipped live connection: no credential available.")
        return result

    # AISStream requires BoundingBoxes as [[[minLat,minLon],[maxLat,maxLon]]]
    subscription = {
        "APIKey": api_key,
        "BoundingBoxes": [[[MIN_LAT, MIN_LON], [MAX_LAT, MAX_LON]]],
        "FilterMessageTypes": ["PositionReport"],
    }
    ssl_ctx = ssl.create_default_context()
    seen_vessels: set[str] = set()
    seen_tw_vessels: set[str] = set()
    deadline = time.monotonic() + seconds
    try:
        async with websockets.connect(AISSTREAM_URL, ssl=ssl_ctx, open_timeout=10) as ws:
            result.connected = True
            # Subscription must be sent within 3 seconds of connecting.
            await ws.send(json.dumps(subscription))
            result.notes.append("Subscription sent within open window.")
            while time.monotonic() < deadline:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
                except asyncio.TimeoutError:
                    break
                result.total_frames += 1
                try:
                    msg = json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    continue
                if result.subscription_confirmed is None:
                    result.subscription_confirmed = True
                # AISStream wraps payloads: {"MessageType": "PositionReport",
                # "MetaData": {...}, "Message": {"PositionReport": {...}}}
                mtype = msg.get("MessageType")
                meta = msg.get("MetaData", {}) or {}
                if mtype == "PositionReport":
                    result.position_frames += 1
                    lat = meta.get("latitude")
                    lon = meta.get("longitude")
                    vid = str(meta.get("MMSI") or meta.get("ShipId") or "")
                    if vid:
                        seen_vessels.add(vid)
                    ts = meta.get("time_utc") or _utc_now_iso()
                    result.latest_message_timestamps.append(str(ts))
                    if _in_taiwan_bbox(lat, lon):
                        result.taiwan_position_frames += 1
                        if vid:
                            seen_tw_vessels.add(vid)
                        if len(result.sample_positions) < 3:
                            result.sample_positions.append(
                                {"lat": lat, "lon": lon, "time_utc": str(ts)}
                            )
            result.unique_vessels = len(seen_vessels)
            result.unique_taiwan_vessels = len(seen_tw_vessels)
    except Exception as exc:  # noqa: BLE001 - smoke test reports any failure
        result.error = f"{type(exc).__name__}: {exc}"
    if result.connected and result.total_frames == 0:
        result.notes.append(
            "Connected but received ZERO frames in the window (known AISStream failure mode)."
        )
    return result


# --------------------------------------------------------------------------- #
# B. Open Waters — WebSocket
# --------------------------------------------------------------------------- #
def _extract_openwaters_position(msg: dict[str, Any]) -> tuple[float | None, float | None, str, str | None]:
    """Best-effort extraction of (lat, lon, vessel_id, timestamp) from an
    Open Waters message. The exact schema is discovered empirically; try the
    common field names."""
    lat = (
        msg.get("lat")
        or msg.get("latitude")
        or (msg.get("position") or {}).get("lat")
        or (msg.get("geometry") or {}).get("coordinates", [None, None])[1]
        if isinstance(msg.get("geometry"), dict)
        else msg.get("lat") or msg.get("latitude")
    )
    lon = (
        msg.get("lon")
        or msg.get("lng")
        or msg.get("longitude")
        or (msg.get("position") or {}).get("lon")
    )
    if isinstance(msg.get("geometry"), dict):
        coords = msg["geometry"].get("coordinates")
        if isinstance(coords, (list, tuple)) and len(coords) >= 2:
            lon, lat = coords[0], coords[1]
    props = msg.get("properties") if isinstance(msg.get("properties"), dict) else msg
    vid = str(
        props.get("mmsi")
        or props.get("id")
        or props.get("vessel_id")
        or msg.get("mmsi")
        or msg.get("id")
        or ""
    )
    ts = props.get("seen") or props.get("timestamp") or props.get("last_seen") or msg.get("timestamp")
    try:
        lat = float(lat) if lat is not None else None
        lon = float(lon) if lon is not None else None
    except (TypeError, ValueError):
        lat = lon = None
    return lat, lon, vid, (str(ts) if ts is not None else None)


async def smoke_openwaters_ws(seconds: int) -> SmokeResult:
    result = SmokeResult(provider="open_waters_ws")
    subscription = {
        "type": "subscribe",
        "bbox": [[MIN_LAT, MIN_LON, MAX_LAT, MAX_LON]],
        "snapshot": True,
    }
    ssl_ctx = ssl.create_default_context()
    seen_vessels: set[str] = set()
    seen_tw_vessels: set[str] = set()
    deadline = time.monotonic() + seconds
    try:
        async with websockets.connect(OPENWATERS_WS_URL, ssl=ssl_ctx, open_timeout=10) as ws:
            result.connected = True
            await ws.send(json.dumps(subscription))
            result.notes.append("Subscription (snapshot:true) sent.")
            while time.monotonic() < deadline:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
                except asyncio.TimeoutError:
                    break
                result.total_frames += 1
                try:
                    msg = json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    continue
                if result.subscription_confirmed is None and isinstance(msg, dict):
                    if msg.get("type") in {"subscribed", "ack", "subscribe"}:
                        result.subscription_confirmed = True
                # Messages may be single features or FeatureCollections / arrays.
                candidates: list[dict[str, Any]] = []
                if isinstance(msg, dict) and msg.get("type") == "FeatureCollection":
                    candidates = msg.get("features", [])
                elif isinstance(msg, dict) and isinstance(msg.get("vessels"), list):
                    candidates = msg["vessels"]
                elif isinstance(msg, list):
                    candidates = msg
                elif isinstance(msg, dict):
                    candidates = [msg]
                for cand in candidates:
                    if not isinstance(cand, dict):
                        continue
                    lat, lon, vid, ts = _extract_openwaters_position(cand)
                    if lat is None or lon is None:
                        continue
                    result.position_frames += 1
                    if vid:
                        seen_vessels.add(vid)
                    if ts:
                        result.latest_message_timestamps.append(ts)
                    if _in_taiwan_bbox(lat, lon):
                        result.taiwan_position_frames += 1
                        if vid:
                            seen_tw_vessels.add(vid)
                        if len(result.sample_positions) < 3:
                            result.sample_positions.append(
                                {"lat": lat, "lon": lon, "seen": ts}
                            )
            result.unique_vessels = len(seen_vessels)
            result.unique_taiwan_vessels = len(seen_tw_vessels)
    except Exception as exc:  # noqa: BLE001
        result.error = f"{type(exc).__name__}: {exc}"
    if result.connected and result.total_frames == 0:
        result.notes.append("Connected but received ZERO frames in the window.")
    return result


# --------------------------------------------------------------------------- #
# B. Open Waters — REST snapshot
# --------------------------------------------------------------------------- #
async def smoke_openwaters_rest() -> SmokeResult:
    result = SmokeResult(provider="open_waters_rest")
    if httpx is None:
        result.error = "httpx not installed; skipped REST snapshot."
        return result
    bbox = f"{MIN_LAT},{MIN_LON},{MAX_LAT},{MAX_LON}"
    url = f"{OPENWATERS_REST_URL}?bbox={bbox}"
    seen_vessels: set[str] = set()
    seen_tw_vessels: set[str] = set()
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(url, headers={"Accept": "application/json"})
            result.notes.append(f"HTTP {resp.status_code} from {url}")
            result.connected = resp.status_code == 200
            if resp.status_code != 200:
                result.error = f"HTTP {resp.status_code}: {resp.text[:200]}"
                return result
            data = resp.json()
            items: list[dict[str, Any]] = []
            if isinstance(data, dict) and data.get("type") == "FeatureCollection":
                items = data.get("features", [])
            elif isinstance(data, dict) and isinstance(data.get("vessels"), list):
                items = data["vessels"]
            elif isinstance(data, list):
                items = data
            for item in items:
                if not isinstance(item, dict):
                    continue
                lat, lon, vid, ts = _extract_openwaters_position(item)
                if lat is None or lon is None:
                    continue
                result.position_frames += 1
                if vid:
                    seen_vessels.add(vid)
                if ts:
                    result.latest_message_timestamps.append(ts)
                if _in_taiwan_bbox(lat, lon):
                    result.taiwan_position_frames += 1
                    if vid:
                        seen_tw_vessels.add(vid)
                    if len(result.sample_positions) < 3:
                        result.sample_positions.append({"lat": lat, "lon": lon, "seen": ts})
            result.total_frames = len(items)
            result.unique_vessels = len(seen_vessels)
            result.unique_taiwan_vessels = len(seen_tw_vessels)
    except Exception as exc:  # noqa: BLE001
        result.error = f"{type(exc).__name__}: {exc}"
    return result


async def main_async(seconds: int, provider: str) -> int:
    print("=" * 70)
    print("SeaWatch Phase 7A — Live Taiwan AIS provider smoke test")
    print(f"Taiwan bbox: minLat={MIN_LAT} minLon={MIN_LON} maxLat={MAX_LAT} maxLon={MAX_LON}")
    print(f"Window: {seconds}s per WebSocket provider; started {_utc_now_iso()}")
    print("=" * 70)

    results: list[SmokeResult] = []
    if provider in {"all", "aisstream"}:
        print(f"\n[A] AISStream.io — connecting ({seconds}s)...")
        results.append(await smoke_aisstream(seconds))
    if provider in {"all", "openwaters"}:
        print(f"\n[B] Open Waters WebSocket — connecting ({seconds}s)...")
        results.append(await smoke_openwaters_ws(seconds))
        print("\n[B] Open Waters REST snapshot — querying...")
        results.append(await smoke_openwaters_rest())

    print("\n" + "=" * 70)
    print("RESULTS")
    print("=" * 70)
    for res in results:
        print(json.dumps(res.summary(), indent=2, ensure_ascii=False))

    usable = [r for r in results if r.usable()]
    print("\n" + "-" * 70)
    if usable:
        print("USABLE Taiwan AIS providers (real position frames observed):")
        for r in usable:
            print(f"  - {r.provider}: {r.taiwan_position_frames} TW frames, "
                  f"{r.unique_taiwan_vessels} unique TW vessels")
    else:
        print("NO provider delivered real Taiwan AIS position frames in this run.")
        print("Do NOT fake success. Report this result and STOP before building live tracking.")
    print("-" * 70)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test free Taiwan AIS providers.")
    parser.add_argument("--seconds", type=int, default=30, help="WebSocket listen window per provider.")
    parser.add_argument(
        "--provider",
        choices=["all", "aisstream", "openwaters"],
        default="all",
    )
    args = parser.parse_args()
    return asyncio.run(main_async(args.seconds, args.provider))


if __name__ == "__main__":
    raise SystemExit(main())
