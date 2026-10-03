# Phase 8 Edge resilience verification report

Date: 2026-10-02 (Asia/Taipei)

## Delivered behavior

SeaWatch retains the public Cloud architecture (Vercel -> Render -> Open
Waters) and adds an opt-in Windows Edge runtime. Cloud Live represents broad
Taiwan network AIS coverage. Edge Live represents only AIS received by the
local VHF antenna through AIS-catcher UDP. Edge Replay is recorded NMEA and is
never labeled RF live. Offline Demo is synthetic, not live. Sustained operation
requires a charged laptop battery or UPS.

The backend owns Cloud and Edge stores independently, uses exact internal MMSI
only for deduplication, publishes keyed opaque vessel IDs, applies monotonic
freshness and Cloud recovery hysteresis, and keeps cached tracks source-owned.
The local production web app uses same-origin relative APIs and a
NLSC -> PMTiles -> bundled-emergency map hierarchy.

## Automated verification observed

- Backend after Slice J: 248 passed; one existing Starlette deprecation warning.
- Frontend after Slice J: 133 passed across 18 files; production build passed
  with the existing large-chunk warning.
- Offline Chromium: 1 passed. Page, assets, live/resilience APIs, and the absent
  PMTiles request all used `http://127.0.0.1:8000`; emergency map rendered; no
  localhost, Vercel, Render, NLSC, CDN, font, glyph, sprite, or other-origin
  request occurred.
- Simulation drill: 3 tests passed and seven `SIMULATED` stages completed,
  including configured recovery hysteresis and replay-only `EDGE_REPLAY`.
- Final Slice L verification: backend 255 passed; frontend 133 passed across 18
  files; TypeScript/Vite production Edge build passed; offline Chromium 1/1
  passed. The only backend warning is the pre-existing Starlette TestClient
  deprecation; frontend emits pre-existing React `act(...)` test warnings and
  Vite emits the existing large-chunk advisory.

## Backend measurements

Command:

```powershell
.\.venv\Scripts\python.exe scripts/measure_edge_resilience.py --fixture tests/fixtures/ais/edge_nmea.txt --iterations 30 --output .swtmp/edge-resilience-measurement.json
```

Environment: Windows 11 `10.0.26200`, AMD64 with 12 logical CPUs, Python
3.12.7, FastAPI 0.115.6, pyais 3.2.3. One warm-up iteration was excluded; 30
samples used 12 fixture lines and decoded 7 position observations per iteration.

| Metric | Median | p95 | Max |
| --- | ---: | ---: | ---: |
| AIS fixture decode | 1.621 ms | 2.594 ms | 2.715 ms |
| Store update | 0.070 ms | 0.112 ms | 0.128 ms |
| Decode + store ingest rate | 4,139 obs/s | 4,402 obs/s | 4,449 obs/s |
| Local `/live/vessels` TestClient | 10.048 ms | 15.602 ms | 60.891 ms |

These are machine-specific fixture/TestClient timings, not radio throughput or
Internet latency. The measurement output privacy scan found no forbidden public
identity fields.

## Browser map measurement

Chromium 153 measured 1,000 generated anonymous GeoJSON points using browser
Performance API marks around `GeoJSONSource.setData` through the next animation
frame. Three warm-ups were excluded; 30 samples produced median 26.8 ms, p95
46.0 ms, and max 98.8 ms. This is a JavaScript scheduling/update scenario, not
a network-latency measurement and not proof that GPU rendering completed.

## Remaining hardware-only acceptance

The automated suite requires no Internet, SDR, AIS-catcher, PMTiles archive, or
production identity key. The following still require real field hardware:

1. Confirm RTL-SDR driver and AIS-catcher recognize the exact receiver.
2. Validate decodable live NMEA on UDP `127.0.0.1:10110` with an installed AIS
   antenna and local vessel traffic.
3. Measure real local RF range/coverage; do not extrapolate it Taiwan-wide.
4. Run a controlled Internet disconnect while RF continues and confirm
   `CLOUD_LIVE -> EDGE_LIVE -> CLOUD_LIVE` after the recovery hold.
5. Measure laptop/UPS runtime under receiver, API, and browser load.
6. Install and validate the chosen licensed Taiwan PMTiles archive/schema.
