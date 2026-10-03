# Datalastic Area Scan to Detection Hook

## Purpose and safety boundary

This integration sends the real, provider-timestamped observations from an operator-initiated Datalastic Area Scan into SeaWatch's existing Detection stack. It surfaces behavioural anomalies as candidates for human review. It does not determine intent, legality, hostility, or wrongdoing, and it does not trigger operational action.

The integration adds no polling and makes no Datalastic request of its own. One uncached Scan Area workflow performs the existing provider query or queries needed to cover the polygon, produces one normalized batch, and delivers that batch to Detection at most once. Cache hits and coalesced waiters reuse the completed result without delivering it again.

## Runtime and data flow

`apps/api/seawatch/live/runtime.py` creates one `LiveDetectionRuntime` alongside the existing process-owned live services. The same `VesselIdentityRegistry` is shared by Area Scan display results and Detection serialization. Runtime mutation and public reads are protected by a re-entrant lock.

The hook is in `AreaScanService._perform_scan()` in `apps/api/seawatch/live/area_scan.py`, after provider validation, reconciliation, normalization, exact polygon `covers()` filtering, and the maximum-result check:

```text
explicit Scan Area
  -> existing Datalastic provider workflow
  -> normalize, deduplicate, exact-polygon filter, validate batch size
  -> existing Area Scan response
  -> one failure-isolated observation sink
  -> LiveDetectionRuntime.update(...)
  -> RollingTrackBuffer -> one fleet-wide engine.analyze(...) call
  -> existing event detectors, fusion, alert policy, and optional ML opinion
```

Only observations with a real provider observation time enter Detection. `received_at`/`scanned_at` is not substituted for missing provider time and cannot create motion. The callback runs in a worker thread so analysis does not block the async event loop.

The three time concepts stay separate:

- `observed_at`: provider fix time used by the rolling track.
- `scanned_at`: time of the Area Scan provider result.
- `analysis_at`: time the Detection analysis completed.

## Track and analysis lifecycle

`LiveDetectionRuntime` lazily creates one `LiveDetectionAnalyzer`, one bounded canonical `RollingTrackBuffer`, and one `DetectionContext`. They are reused across scans rather than rebuilt per request or vessel. The adapter retains its canonical deduplication, point-retention, vessel-staleness, expiry, historical-read, capacity, and fleet eligibility semantics.

The first scan normally supplies only one fix per vessel. Those fixes start tracks, but existing eligibility requirements remain unchanged, so the honest state is usually `insufficient_history` and no trajectory alert is invented. Later operator-initiated scans can append genuine fixes. Exact repolls do not grow track history. Each update sends all currently eligible tracks to one `engine.analyze(...)` call so multi-vessel detectors retain fleet context.

The latest successful `AnalysisResult` remains readable if a later analysis fails. State is bounded by the existing adapter limits and the live 15-minute vessel freshness setting; there is no external persistence, so accumulated state resets with the API process.

## Detection context and optional ML

The live runtime reuses the Detection service's learned/historical context and feedback/watch state when real learned context is available. It clones only the mutable per-analysis statistics so live and scenario analysis cannot corrupt one another. When the selected Detection service has only simulated context, live analysis does not consume that simulated baseline: it uses canonical static geographic context and reports `context_quality=static_only`, which makes the result `degraded` rather than pretending historical context exists.

The deterministic Detection stack remains primary. If its existing loaded ML bundle is available and deterministic fusion has produced alert candidates, the runtime reuses the existing window features and `score_alert` contract to attach the existing second opinion. No model is trained or synthesized here. With no model, `ml_available=false` and alert ML remains absent; an ML scoring error is isolated, clears the affected optional opinions, and reports a degraded status without discarding deterministic results.

Core live Detection never calls an LLM. Live alert detail returns no path-agent reviews (`path_reviews=[]`), so no path-analysis/LLM request is made by a scan or by the live Watch Floor read path.

## Status and failure behaviour

The Area Scan response includes a separate additive `detection` object. Live Detection reads also expose status and safe provenance through `GET /detection/scenario?source=live`.

- `ready`: eligible analysis completed with available historical context.
- `insufficient_history`: no track is yet eligible for analysis.
- `degraded`: deterministic analysis completed using static-only context or optional ML scoring failed.
- `context_unavailable`: Detection dependencies could not be created.
- `error`: analysis failed; the last successful result remains available.

A successful paid Area Scan remains successful if Detection initialization, deterministic analysis, or optional ML raises. The failure is represented only in the Detection status, and logs contain a generic message rather than provider data or secrets. A failed provider workflow never invokes the Detection sink and therefore cannot fabricate an update.

## Identity and API

Detection may retain MMSI internally for canonical joins and detector behaviour. Before browser serialization, all live tracks, alert summaries, alert details, events, evidence strings, and nested values pass through the shared `VesselIdentityRegistry` mapping and recursive redaction. The compatible `mmsi` fields contain opaque IDs for live responses, and explicit `public_id`/`public_ids` fields are also present. Raw MMSI, IMO, provider UUID, and credentials are not exposed by the new live Detection contract.

Because Area Scan and live Detection share the registry, the Area Scan vessel `public_id`, live track `public_id`, and alert vessel `public_id` resolve to the same browser-safe vessel identity. Names, IMO values, provider UUIDs, and flags are not used to fabricate cross-source joins.

Existing `/detection/*` scenario/replay behaviour remains the default. The following operations accept `source=live`:

- `GET /detection/scenario`
- `GET /detection/tracks`
- `GET /detection/alerts`
- `GET /detection/alerts/{alert_id}`
- `POST /detection/alerts/{alert_id}/status`
- `POST /detection/alerts/{alert_id}/notes`

Live alerts do not accept replay `as_of` queries. Feedback status and notes are scoped to the selected source.

## Watch Floor

The existing Watch Floor has a `Scenario replay` / `Live Area Scan` selector. Live mode reloads the same queue, map, alert detail, evidence, uncertainty, benign-explanation, timeline, optional ML, status, and note components with `source=live`. It displays the live Detection status and opaque `Vessel ID`. Replay, truth/evaluation, and tuning controls are hidden because they are scenario-only. Returning to scenario mode restores them without changing the backend region selection.

## Current limitations

- Live accumulated tracks are process-local and are lost on API restart.
- Detection receives only provider-timestamped fixes. Vessels with missing provider times can still appear in the Area Scan response but cannot contribute motion evidence.
- Enough elapsed real fixes must accumulate before trajectory-dependent detectors become eligible; there is no interpolation or synthetic demo alert.
- Static-only context is explicitly degraded. The separate SSD historical-data integration is not part of this hook.
- No hidden polling is added. A human must perform later scans to accumulate new fixes.
- Detection cannot improve provider freshness and does not dead-reckon positions.

## Local performance observation

A no-network synthetic sample matching the previous 96-vessel Area Scan scale took 0.0216 seconds for the one-fix/insufficient-history update and 0.0684 seconds for the second accumulated fix and one fleet-wide deterministic analysis on this development machine. The second pass analyzed all 96 vessels and produced no fabricated events or alerts. This sample used no ML bundle and no provider I/O; latency with eligible complex behaviours, ML scoring, or a larger fleet can be higher. The canonical adapter's separate 1,000-vessel/8,000-point benchmark remains documented in `docs/live-detection-adapter.md`.

## Manual real-Datalastic E2E (human-operated only)

Do not run this procedure from automated tests. It consumes provider quota.

1. Configure the API with a valid Datalastic key and the existing Area Scan access settings, then start the API and web app through the normal local workflow.
2. On the Live Map, draw a small rectangle or polygon. Confirm `/live/area-scan/plan` reports an acceptable plan before submitting.
3. Select **Scan Area** once. Confirm the response is HTTP 200, the provider query count is expected for the plan, real vessels appear, and the separate `detection` object reports its honest status.
4. Open Watch Floor, select **Live Area Scan**, and confirm its vessel/fix counts and Detection status match the completed scan. A first scan may correctly show `insufficient_history` with no alerts.
5. After providers have produced later fixes, explicitly scan the same area again. Confirm tracks have accumulated genuine timestamps and exact unchanged repolls have not added points.
6. If existing rules and eligibility produce a candidate, confirm it appears in the existing Alert Queue, opens in the existing Alert Panel, links to the same opaque vessel ID as the map, and retains reasons, uncertainty, benign alternatives, and human-review controls.
7. If an existing ML bundle is loaded, confirm any opinion is labeled as the optional statistical second opinion. If none is loaded, confirm the deterministic result still works and no ML result is shown.
8. Exercise a test-only/local injected Detection failure if available and confirm the paid Area Scan result still succeeds while Detection reports a degraded/error state. Do not simulate a failure by spending another provider request.
