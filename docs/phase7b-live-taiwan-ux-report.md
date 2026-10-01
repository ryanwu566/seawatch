# Phase 7B — Live Taiwan Maritime Awareness Experience

Branch: `feat/live-taiwan-ux`
Builds on Phase 7A live foundation (commit `e4f4d54`). The real-time Open Waters
ingest, store, and `/live/*` API were **not** modified in this phase.

## 1. AISStream secondary validation result

`AISSTREAM_API_KEY` is still **not present** in the environment. The 30-second
Taiwan smoke test (`scripts/smoke_test_live_ais.py --provider aisstream`)
returned `error: AISSTREAM_API_KEY not set`, `usable: false`, zero Taiwan frames.
AISStream was therefore **not** registered as a failover provider (an unvalidated
provider must not be registered). Open Waters remains the sole/primary provider.
The `LiveAisProvider` abstraction already supports adding AISStream later when a
key exists. No UI work was blocked on this.

## 2. Bilingual UX changes

- `src/i18n/dictionaries.ts` + `I18nContext.tsx`: structured dictionaries, no
  per-language component duplication.
- Default **Traditional Chinese** (`zh-Hant`), secondary **English**.
- Top-right `中文 | EN` toggle switches **instantly without reload** and persists
  to `localStorage`.
- Friendly, non-technical first-level wording: 需關注船舶 / Vessels to Review,
  關注程度 / Review Priority, 為什麼值得注意 / Why It Was Flagged, 判斷依據 /
  Supporting Evidence. Percentile/feature/method details live under 進階分析 /
  Advanced Analysis. Prohibited vocabulary (threat/enemy/hostile/illegal) avoided.

## 3. Live vessel motion behavior

- Backend positions are never fabricated. Frontend **visual interpolation**
  (`src/lib/interpolation.ts`) dead-reckons the marker between real fixes using
  the last measured position, SOG, and course/heading (great-circle projection,
  capped at 120 s so a lost vessel does not drift forever).
- A `requestAnimationFrame` loop in `MapCanvas` advances visual positions each
  frame and reconciles toward each new real fix (no teleport).
- The UI always shows the AIS fix age (`資料更新：X 秒前 / AIS fix: X sec ago`)
  and labels state via badges. Provider `synthesized=true` is surfaced
  separately as 供應商插值 / Provider Interpolated, distinct from frontend
  視覺平滑 / Visual Interpolation.

## 4. Taiwan basemap implementation

- `src/config/taiwanMap.ts` builds MapLibre raster styles for the official NLSC
  WMTS services: 臺灣通用電子地圖 (EMAP) and 正射影像 (PHOTO2), EPSG:3857.
- Base-map toggle in the layer control switches via `map.setStyle()`; overlays
  are reinstalled on `styledata`. Attribution (© 內政部國土測繪中心 NLSC) is
  kept visible. Tiles are fetched on demand — no bulk caching.
- Honest CORS handling: `MapCanvas` listens for tile/source errors and raises
  `onBaseMapError`, which shows a note in the UI instead of faking success. (NLSC
  tile reachability from a browser was not verified in this headless environment;
  the fallback path is wired and labeled.)

## 5. Maritime public layers

- Public commercial ports (civilian): 基隆、臺北、臺中、高雄、花蓮、安平, drawn as
  a labeled circle+symbol layer. Grouped under 海事圖層 / Maritime Layers.
- No live ROC Navy positions, military deployments, sensitive facilities, or
  operational routes.

## 6. Airspace public layers

- 空域圖層 / Airspace Layers: an illustrative public Taipei FIR boundary polygon
  as **context only** (dashed outline + faint fill). No live aircraft, no radar
  tracks, no operational military data. Context features carry no position/speed
  fields (asserted in tests).

## 7. Vessel detail interaction

- Clicking a ship symbol opens `VesselPanel` (side panel on desktop, bottom sheet
  on mobile). Traditional-Chinese-first fields: 船舶概況、目前航速、航向、船首向、
  目的地、最近更新、資料來源、最近航跡、關注程度、為什麼值得注意.
- Trail: fetches `GET /live/vessels/{id}/track`; draws the recent trail when ≥2
  points, else shows 航跡累積中 / Building Track History. Live vessels show
  資料累積中 / Collecting trajectory for review priority (no fabricated score).
- Advanced Analysis (collapsed by default) shows method, percentile, supporting
  features, data quality, benchmark source, and the NOT-Taiwan-validated
  disclaimer. MMSI/IMO never required or shown.

## 8. Data-integrity labeling

`IntegrityBadge` + `src/lib/integrity.ts` classify every vessel into one of:
即時 AIS / Live AIS, 快取 / Cached, 資料較舊 / Stale, 供應商插值 / Provider
Interpolated, 視覺平滑 / Visual Interpolation, 離線展示 / Offline Demo. States are
never blurred. Offline demo only under `VITE_DEMO_MODE=true`, visibly labeled.

## 9. Performance measurements

Live end-to-end (real Open Waters, 20 s warm-up, this run):

| Metric | Value |
| --- | --- |
| Upstream message rate | 86.2 msg/sec |
| Live vessel count | 1,634 |
| `/live/vessels` payload (full country) | 671.6 KB |
| `/live/vessels` latency (full, first call) | ~160 ms |
| Health | online, connected, 0 reconnects, msg age 4.5 s |

Store-served latency (warm store, serialization only, from Phase 7A bench):

| Query | Vessels | Payload | Median latency |
| --- | --- | --- | --- |
| Full country | 1,600 | 566 KB | 47.6 ms |
| Viewport bbox (0.5°×0.5°) | 204 | 72 KB | 12.7 ms |

Frontend: polls `/live/vessels` every 8 s using the **viewport bbox**, with a
400 ms debounce on map movement, so the payload matches the visible area rather
than the whole country. Smooth motion comes from client-side interpolation, so
the poll cadence stays low. Rendering uses one MapLibre GeoJSON source +
`setData` (no DOM element per vessel). Build size: JS 988.73 KB (277.54 KB
gzip), CSS 76.6 KB (11.9 KB gzip).

MapLibre per-frame source-update time was not instrumented in this environment;
the single-source `setData` design is the mechanism that keeps it cheap.

## 10. Tests

- Frontend: **59 passed** (10 files). Covers: zh-Hant default + English toggle;
  visual interpolation (advance / zero-speed / unknown course / reconcile);
  integrity classification incl. measured-vs-provider-interpolated and offline
  demo; vessel panel open/fields/track states/advanced; layer toggle + basemap
  switch; status card live count; MapCanvas single-source + heading→COG
  orientation + viewport bbox emit + click-selects; NLSC basemap config; ports
  within bbox; airspace context-only.
- Backend: **191 passed** (unchanged; `-p no:cacheprovider --basetemp=...\.swtmp`).
- `npm run build` succeeds.

## 11. Local run instructions

Backend (serves the live store; one upstream Open Waters feed):

```
cd C:\Projects\seawatch
set SEAWATCH_LIVE_INGEST=true
python -m uvicorn apps.api.seawatch.main:app --port 8000
```

Frontend (Taiwan product is the default route):

```
cd C:\Projects\seawatch\apps\web
npm run dev
# open http://localhost:5173  (live Taiwan experience, zh-Hant default)
# http://localhost:5173?research  -> original Phase 3B research dashboard
```

Offline demo (clearly labeled, never silently substituted):

```
# apps/web/.env
VITE_DEMO_MODE=true
```

Tests:

```
python -m pytest -q -p no:cacheprovider --basetemp=C:\Projects\seawatch\.swtmp
cd apps/web && npm test && npm run build
```

Screenshots: not captured in this headless CLI environment. The run instructions
above reproduce the UI locally (map-first Taiwan view, status cards, layer
control, click-to-open vessel panel, 中文/EN toggle).
