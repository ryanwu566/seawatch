# Phase 7A — Real-Time Taiwan AIS Foundation Report

Branch: `feat/live-taiwan-ux`
Date: 2026-10-01 (UTC)
Taiwan bounding box tested: `minLat 21.5, minLon 118.0, maxLat 26.5, maxLon 123.5`

This phase validated FREE real-time AIS providers for Taiwan **before** building
any UI, then implemented the backend live-data foundation and a minimal frontend
map proof. Nothing is synthesized in the live path.

## 1. Provider smoke-test results

Reusable script: `scripts/smoke_test_live_ais.py` (reads credentials from the
environment only; never prints them).

### A. AISStream.io (`wss://stream.aisstream.io/v0/stream`)

- **SKIPPED / not validated.** No `AISSTREAM_API_KEY` was present in the
  environment. AISStream requires a free API key; without it the socket delivers
  zero messages. `connected=false`, `usable=false`.
- A successful connection alone would not have counted as success; real Taiwan
  position frames are required. None could be observed without a key.

### B. Open Waters (`wss://ais.openwaters.io/v1/stream`, anonymous)

Observed in a 30-second window over the Taiwan bbox:

| Metric | WebSocket | REST snapshot |
| --- | --- | --- |
| Connection | ✅ connected | HTTP 200 |
| Total frames | 3,288 | 1,963 features |
| Position frames | 3,287 | 1,963 |
| Unique vessels | 1,465 | 1,963 |
| Taiwan-bbox frames | 3,285 | 1,963 (all) |
| Freshness | seconds old | `seen` timestamps seconds old |
| Credential | none (anonymous) | none |

The REST FeatureCollection reported `truncated: true` at 1,963 features (an
anonymous cap). The WebSocket `snapshot:true` warm-up plus the live stream is the
primary ingest path.

## 2. Selected provider

**Open Waters** is the primary provider. It delivered real, fresh Taiwan AIS
(~1,465–1,963 unique vessels, timestamps seconds old) with no credential. The
provider abstraction (`LiveAisProvider`) allows adding AISStream failover later
if a key becomes available.

Anonymous Open Waters limits (from the welcome ack): 2 connections, rate 20,
area 100 sq-degrees, 10 mmsis, 20 connects/min. The Taiwan bbox is ~27.5
sq-degrees — within the anonymous area limit.

The `synthesized` flag on each frame indicates provider-interpolated positions;
it is preserved end-to-end so the UI can distinguish measured fixes from
interpolation.

## 3. Live architecture

```
Open Waters WS (one upstream connection, Taiwan bbox subscription)
        │  AisIngestConsumer (asyncio task, exponential backoff reconnect)
        ▼
OpenWatersProvider.parse_frame()  → normalized LiveVesselObservation
        ▼
LiveVesselStore (in-memory, threading.RLock)
   • dedup by provider_id
   • latest observation + rolling 30-min trajectory
   • stale cleanup (15 min)
        ▼
GET /live/health | /live/vessels | /live/vessels/{id}/track   (read-only, no upstream call)
        ▼
Frontend LiveMap (one MapLibre GeoJSON source, setData, ?live mode)
```

One backend upstream feed → one shared store → many fast API reads. The frontend
never contacts Open Waters directly.

## 4. API endpoints

- `GET /live/health` — connection, subscription, last-message freshness, vessel
  count, reconnect attempts, provider, bbox.
- `GET /live/vessels[?min_lat&min_lon&max_lat&max_lon]` — GeoJSON FeatureCollection;
  per-vessel `observed_at`, `source`, `data_age_seconds`, `synthesized`; no MMSI/IMO.
- `GET /live/vessels/{id}/track` — rolling real trajectory as a GeoJSON LineString.

## 5. Minimal Taiwan map proof

- `?live` URL mode renders `LiveMap` instead of the dashboard.
- Centered on Taiwan; polls `/live/vessels` every 30s.
- One MapLibre GeoJSON source + one circle layer; updated via `source.setData()`
  without remounting. No React component per vessel.
- Marker color distinguishes measured (blue) vs provider-interpolated (amber).
- Orientation prefers heading, falls back to COG, else neutral.
- End-to-end run: **1,606 real Taiwan vessels** present in the store, health
  `online`, connected, 0 reconnects.

## 6. Performance measurements

Live end-to-end (real Open Waters, 20s warm-up):

| Metric | Value |
| --- | --- |
| Upstream message rate | 85.5 msg/sec |
| Current vessel count | 1,606 |
| `/live/vessels` payload (all vessels) | 660 KB |
| Health | online, connected, 0 reconnects, msg age 7s |

Store-served latency (warm store, serialization only, no upstream):

| Query | Vessels | Payload | Median latency |
| --- | --- | --- | --- |
| Full country | 1,600 | 566 KB | 47.6 ms |
| Viewport bbox (0.5°×0.5°) | 204 | 72 KB | 12.7 ms |

Reads perform no external network call. Viewport bbox filtering cuts payload and
latency substantially; the frontend uses it for the active viewport.

Scripts: `scripts/live_proof_measure.py` (live), ad-hoc viewport bench.

## 7. Data integrity

Every live vessel carries `observed_at` (upstream report time), `source`,
`data_age_seconds` (server-computed), and `synthesized`. The backend never
fabricates positions or timestamps and never substitutes synthetic fixtures into
the live endpoints. A single-point trajectory yields a 1-point LineString rather
than an invented segment.

## 8. Tests

- Backend: `tests/unit/test_live_ais.py` — 20 tests (normalization for WS + REST,
  AIS sentinels → None, store update/dedup/trajectory/stale/bbox, reconnect/health
  state, all three endpoints, identity never exposed, no credentials required).
  Full suite: **191 passed**.
- Frontend: `src/components/LiveMap.test.tsx` — 3 tests (Taiwan init center, LIVE
  indicator + freshest age, single GeoJSON source via setData + orientation).
  Full suite: **29 passed**. `npm run build` succeeds.

Run backend tests on this Windows environment with:

```
python -m pytest -q -p no:cacheprovider --basetemp=C:\Projects\seawatch\.swtmp
```
