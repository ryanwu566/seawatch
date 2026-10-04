# Historical Runtime v2 UI Integration Design

## Intent and scope

Integrate the already-verified SeaWatch Historical Runtime v2 bundle into the current final SeaWatch backend and make its availability, scale, provenance, and limitations visible in the Watch Floor. Historical context is optional reference data: the application, Live Detection Hook, Datalastic Area Scan, and scenario replay must continue to operate when the bundle is absent or unreadable.

This change ends at the compact backend adapter, privacy-safe `GET /detection/historical` endpoint, typed frontend client, compact `HistoricalRuntimeCard`, tests, and verification. It does not add the 2,457-cell traffic heatmap, per-alert historical context, live-vessel historical joins, new detection behavior, or changes to the existing Vessel Intelligence historical-baseline API.

## Runtime resolution and lifecycle

The adapter resolves the compact bundle in this order:

1. `SEAWATCH_HISTORICAL_RUNTIME`, when set, is the full bundle path.
2. Otherwise, when `SEAWATCH_DATA_ROOT` is set, append `historical_2026/runtime/SeaWatch_Runtime_Taiwan_2026_v2`.
3. When neither variable is set, historical context is unavailable.

No drive letter or machine-specific path is a code default. Resolution is lazy, so importing the API and starting the application never depends on the SSD. The loader reads only the six compact runtime artifacts: `detection_context.joblib`, `vessel_habits.parquet`, `historical_baselines.parquet`, `traffic_context.parquet`, `source_metadata.json`, and `data_quality_report.json`. It never scans the 33-million-row source dataset.

The loaded bundle and its derived indexes are process-cached. A test-only/public cache reset seam permits deterministic tests and intentional artifact refreshes. Repeated endpoint calls reuse the loaded objects instead of rereading Parquet.

## Backend adapter and identity policy

`apps/api/seawatch/detection/historical_runtime.py` is ported semantically from commits `a3701f3` and `2f2df28`, with the hardcoded drive fallback removed. It loads the compact artifacts, normalizes pandas and NumPy scalar values, exposes a whitelisted summary, supports internal conservative MMSI lookup, and provides coarse 0.1-degree traffic-cell lookup for backend use and focused tests.

The cross-source identity index contains only rows whose `mmsi_join_status` is `unique_9digit_candidate`. The MMSI must also be exactly nine decimal digits, and duplicate safe-candidate MMSIs fail the runtime invariant. Rows marked `shared_9digit`, `non_9digit`, or `missing` are never indexed for conservative joining. MMSIs are not padded, truncated, inferred, or fabricated.

Internal lookup records may contain source identifiers because backend consumers need them to inspect the verified artifact, but the new HTTP endpoint exposes only aggregate summary fields. No per-vessel or per-cell HTTP route is introduced in this change.

## HTTP contract and privacy boundary

`GET /detection/historical` is added to the current detection router without replacing or changing any existing scenario or `source=live` route. The route delegates to a small service method that treats missing or unreadable optional artifacts as an unavailable summary rather than an application failure.

The available response is a strict aggregate allowlist:

- `available`
- `runtime`
- `data_model`
- `date_range`
- `row_count`
- `unique_vessel_count`
- `traffic_cell_count`
- `dataset_hour_buckets`
- `mmsi_join_status_counts`

`runtime` is the public bundle name `SeaWatch_Runtime_Taiwan_2026_v2`, never a filesystem path. The unavailable response contains `available: false` and a stable non-sensitive reason. Responses never expose the resolved local path, raw MMSI values, GFW `vesselId`, credentials, or raw artifact records. Both available and unavailable cases return HTTP 200 so optional historical context cannot break Detection UI startup.

The existing `/historical/vessels/{public_id}/baseline` Vessel Intelligence contract remains unchanged and conceptually separate. No Runtime v2 match is claimed for a Vessel Intelligence card or live alert.

## Frontend client and fetch lifecycle

A dedicated typed Historical Runtime client uses the existing shared `getJson`/API-base policy. It supports local development through the existing loopback base behavior and deployed same-origin proxying without hardcoded hosts or storage paths.

`HistoricalRuntimeSummary` models the aggregate endpoint and remains distinct from the existing Vessel Intelligence baseline types. The `HistoricalRuntimeCard` owns its optional request lifecycle. It fetches once when mounted and does not depend on Watch Floor source, alerts, selected alert, replay clock, or Detection refresh state. Consequently those state changes do not trigger refetches. The request is aborted on unmount; a remount starts a new session request. No broader query library or global cache is added because the existing application has no such pattern and once-per-mount behavior is sufficient.

Endpoint failure is caught inside the card and converted to the same calm unavailable presentation as `available: false`. It does not modify `useWatch.error`, readiness, or any scenario/live fetch sequence.

## Historical Runtime card

The card is placed at the top of the existing Watch Floor alert sidebar, below its panel heading and above alert filters. This keeps it visible in scenario and Live modes without enlarging the global header or restructuring the three-column floor.

The compact English states are:

- Loading: a small neutral loading indicator labeled `Loading historical context`.
- Unavailable: `Historical context unavailable`, with no catastrophic red treatment.
- Available: runtime availability, Jan 1–Sep 29, 2026 coverage, `33.2M observations`, `400.8K vessels`, `2,457 traffic cells`, `6,528 hourly buckets`, and `66,043 conservative join candidates`.

The available state visibly identifies the source as `GFW standardized hourly vessel presence` and includes `Not raw/message-level AIS`. Observation wording is `historical presence observations`, never AIS messages. A small explanatory note states that only dataset-internal one-to-one nine-digit MMSI candidates are eligible for conservative cross-source matching.

Formatting utilities compact million and thousand headline counts while retaining locale grouping for traffic cells, hourly buckets, and conservative candidates. The card renders only aggregate allowlisted fields, so even an unexpected additional API property cannot display paths or identifiers.

## Testing strategy

Backend tests create temporary compact-bundle fixtures or mock compact readers at their boundaries; they never depend permanently on `D:\`. Tests cover explicit and fallback resolution, absent and valid bundles, aggregate privacy, safe-only MMSI indexing, rejection of shared or invalid MMSIs, 0.1-degree traffic lookup, compact artifact reads, no raw-dataset scan, endpoint success, and absent-bundle degradation. Cache tests verify a second summary request does not reread the compact artifacts.

Frontend tests cover the typed request path, loading state, available statistics and compact formatting, unavailable and network-failure states, conservative candidate wording, visible hourly-presence/raw-AIS disclaimer, and absence of local paths, MMSIs, and GFW IDs. Watch Floor integration tests verify the card remains mounted and does not refetch while source, alerts, or selection changes, and that card failure does not affect Live mode.

Tests are written and observed failing before production implementation, then rerun green. Verification includes focused historical backend tests, current Detection API tests, focused Watch Floor tests, broader backend and frontend suites when feasible, `npx tsc --noEmit`, `npm run build`, and `git diff --check`.

## Performance and manual verification

The local manual run uses `SEAWATCH_HISTORICAL_RUNTIME` to point at the verified SSD bundle. First and second `GET /detection/historical` latency are measured separately; the second demonstrates cached behavior. A rough process-memory observation is recorded when it can be obtained without adding tooling.

Manual UI verification confirms all five formatted counts and the standardized-hourly-presence disclaimer while ensuring no SSD path appears. Cloud or local runs without the bundle show the unavailable state and retain functioning Detection and Live Area Scan behavior.

## Explicit exclusions and invariants

This change does not add a traffic heatmap or any other map visualization. It does not change Detection thresholds, models, EEZ/12 NM/24 NM geometry, Datalastic behavior, Area Scan semantics, live identity behavior, the canonical runtime files, Vercel configuration, or package versions other than ensuring the existing requirements include `joblib==1.6.0` and retain `uvicorn`.

No historical observation is represented as raw or message-level AIS. No shared, malformed, or missing MMSI is represented as a safe join. No commit or push is performed.
