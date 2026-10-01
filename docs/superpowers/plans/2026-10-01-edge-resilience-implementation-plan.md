# SeaWatch Phase 8 Edge Resilience Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add honest Cloud-to-local-AIS failover and a completely local Windows Edge application without regressing the existing Open Waters Cloud Live path.

**Architecture:** Keep independent Cloud and Edge stores behind a monotonic `ResilienceModeManager` and provenance-aware `ActiveVesselView`. Preserve `/live/*` through additive contracts, then add explicit Edge ingest, frontend mode UX, optional same-origin static serving, and NLSC → PMTiles → emergency-map fallback.

**Tech Stack:** Python 3.12, FastAPI/Starlette, asyncio UDP, pyais, React 18, TypeScript, Vite, MapLibre GL JS, PMTiles JS, Vitest, pytest, Playwright Chromium.

**Spec:** `docs/superpowers/specs/2026-10-01-edge-resilience-design.md`

## Global Constraints

- Base branch is `feat/edge-resilience`; approved design HEAD is `e81d1ab5628eacd90d7525dbde20b31f32a6f85b`.
- The deployed default remains `Browser → Vercel frontend → Render FastAPI → Open Waters`.
- Open Waters parsing, subscription, reconnect behavior, and Taiwan bbox remain unchanged unless a failing compatibility test proves a narrow correction necessary.
- Edge ingest, replay, Offline Demo, local frontend serving, and the drill are disabled unless their explicit flags are enabled.
- Cloud and Edge own separate stores, health, freshness, counters, observations, and tracks.
- Automatic modes are `CLOUD_LIVE`, `EDGE_LIVE`, `EDGE_REPLAY`, and `NO_LIVE_SOURCE`; `OFFLINE_DEMO` is explicit only.
- Defaults are cloud stale `30s`, edge stale `30s`, and cloud recovery `20s`; elapsed decisions use an injected monotonic clock.
- Edge UDP defaults to `127.0.0.1:10110`; no public bind is a normal configuration.
- Replay is always labeled replay/simulated and is never described as live RF.
- Public API/UI must expose no MMSI, IMO, callsign, raw source identifier, or enumerable unkeyed identity.
- Edge coverage is `local_rf` and always says “Shows only vessels receivable by the local antenna.”
- Cached/stale observations retain original provenance; Cloud and Edge tracks are never spliced.
- Local web serving defaults off. When enabled, the prepared Vite `dist`, APIs, PMTiles, and emergency map use `http://127.0.0.1:8000` with no Internet or npm dev server.
- Frontend API-base precedence is: explicit `VITE_API_BASE_URL`; otherwise `http://localhost:8000` only in Vite development; otherwise empty string/same origin in every production build. An Edge build needs no `.env` file and must not contain the Render URL.
- The browser PMTiles URL is always `/offline/taiwan.pmtiles`; `SEAWATCH_PMTILES_FILE` chooses the runtime filesystem file.
- Do not commit PMTiles archives, secrets, raw AIS collections, military data, deployment changes, or Challenge #10 logistics.
- Normal tests require no Internet, RTL-SDR, AIS-catcher, PMTiles archive, or production identity secret.
- Backend full-suite command: `python -m pytest -q -p no:cacheprovider --basetemp=C:\Projects\seawatch\.swtmp`.
- Frontend commands: `cd apps/web`, `npm test`, `npm run build` (use `npm.cmd` under restrictive Windows PowerShell execution policy).
- Follow red/green/refactor for every production behavior: write the test, observe the expected failure, implement minimally, and rerun the focused plus relevant regression suites.
- Stop immediately at a failed hard gate. Do not start the next slice until the gate is green.

## Dependency Review

| Package | Decision and purpose | Why existing/stdlib is insufficient | License | Windows compatibility | Scope |
|---|---|---|---|---|---|
| `pyais==3.2.3` | Add in Slice D to parse checksummed AIVDM/AIVDO, multipart payloads, and AIS message fields. | Correct six-bit AIS decoding and message-type/sentinel handling are protocol-heavy; implementing bitfields from scratch violates the design. | MIT | Python 3.9+, OS-independent `py3-none-any` wheel; verify transitive wheels on Python 3.12 Windows during Slice D. | Backend runtime |
| `pmtiles==4.5.0` | Add in Slice J and bundle its `Protocol` MapLibre adapter into Vite output. | MapLibre has no built-in PMTiles directory/range protocol implementation. | BSD-3-Clause | Browser ES module; PMTiles changelog explicitly supports MapLibre GL JS 4.x and Chrome/Windows behavior. | Frontend runtime |
| `@playwright/test==1.63.0` | Add in Slice J for a real Chromium test that blocks non-loopback traffic and verifies the built local shell/emergency map. | Vitest/jsdom cannot exercise browser networking, WebGL/MapLibre initialization, or prove the built application has no remote asset dependency. | Apache-2.0 | Supports Windows and Node 24. Browser binaries are installed before disconnection; tests make no download attempt. | Frontend dev-only |

Official review sources: PyPI/GitHub for `pyais`, npm/Protomaps PMTiles repository for `pmtiles`, and npm/Playwright documentation for `@playwright/test`. Pin exact versions in lockfiles. Do not add `pyais` before Slice D or frontend packages before Slice J.

## File Structure

| Path | Responsibility |
|---|---|
| `apps/api/seawatch/live/config.py` | Parse validated runtime settings from an injected environment mapping. |
| `apps/api/seawatch/live/resilience.py` | Shared enums/health/status contracts and later the mode manager. |
| `apps/api/seawatch/live/runtime.py` | Own Cloud and Edge state and compose identity/view/manager services. |
| `apps/api/seawatch/live/identity.py` | Keyed opaque IDs and reverse source bindings. |
| `apps/api/seawatch/live/active_view.py` | Active/cached public observations and provenance-aware tracks. |
| `apps/api/seawatch/live/edge_ais.py` | Pure NMEA/AIS decoding and normalization. |
| `apps/api/seawatch/live/edge_ingest.py` | UDP/replay lifecycle and Edge health counters. |
| `apps/api/seawatch/api/resilience.py` | `/resilience/status` and `/edge/health`. |
| `apps/api/seawatch/web/serving.py` | Optional Vite-dist, SPA fallback, and range-capable PMTiles serving. |
| `apps/web/src/api/client.ts` | Select explicit cloud API URL, development localhost convenience, or production same-origin API paths. |
| `apps/web/src/lib/resilience.ts` | Frontend mode/provenance derivation and transition detection. |
| `apps/web/src/config/offlineMap.ts` | PMTiles protocol/style and emergency-style selection. |
| `apps/web/src/components/ResilienceBanner.tsx` | Non-blocking transition and coverage/power messaging. |
| `apps/web/src/assets/taiwan-emergency.geojson` | Lightweight licensed Taiwan outline for zero-network display. |
| `apps/web/e2e/offline-edge.spec.ts` | Real-browser loopback-only application test. |
| `scripts/resilience_drill.py` | Explicit simulation using the real manager. |
| `scripts/measure_edge_resilience.py` | Reproducible latency/rate measurements. |

## Review Focus

1. **Conflicting/invalid environment values:** defaults remain safe, replay cannot enable implicitly, and a configured non-loopback Edge bind emits one explicit security warning while never becoming the default (Slice A tests).
2. **Multipart collisions and resource exhaustion:** duplicate/out-of-order fragments, reused sequence IDs, oversized datagrams, and expired assemblies never mix vessels or grow unbounded (Slices D/E tests).
3. **Clock anomalies:** a decreasing/frozen monotonic test clock cannot create negative age, premature recovery, or mode flapping (Slice F tests).
4. **Origin, route shadowing, and traversal:** production-without-env stays same-origin, SPA fallback never captures API/offline/assets, and configured dist/PMTiles paths cannot escape validated files (Slices I/J tests).
5. **Range/network edge cases:** suffix/open-ended/invalid PMTiles ranges behave correctly, and the offline browser test fails on any non-loopback request including fonts, glyphs, sprites, CSS, or tiles (Slice J tests).

---

## Slice A — Foundation and pure contracts

**Files:**
- Create: `apps/api/seawatch/live/config.py`
- Create: `apps/api/seawatch/live/resilience.py`
- Create: `tests/unit/test_live_config.py`
- Create: `tests/unit/test_resilience_contracts.py`
- Modify: none

**Interfaces:**
- Produce `OperatingMode`, `EdgeInputKind`, `CoverageKind`, `ObservationOrigin`, and `DisplayState` string enums.
- Produce immutable input `SourceHealthSnapshot(source, connected, last_message_at, last_message_monotonic, vessel_count, input_kind)`, computed output `SourceStatus(source, fresh, message_age_seconds, vessel_count, connected, input_kind)`, and `ResilienceStatus(mode, coverage, simulated, cloud: SourceStatus, edge: SourceStatus, power_mode)`.
- Produce immutable `LiveRuntimeConfig.from_env(environ: Mapping[str, str]) -> LiveRuntimeConfig` with typed defaults from the spec.
- No current singleton, API, or startup code consumes these contracts yet.

**Risk / rollback:** Low. New isolated modules only. Delete the four new files to roll back.

**Independent commit:** Yes; no Cloud behavior changes.

- [ ] **A1 — Write failing contract/config tests**

Test exact enum wire values; 30/30/20 timing defaults; `127.0.0.1:10110`; `SEAWATCH_SERVE_WEB=false`; explicit replay enable plus file; invalid/NaN/infinite/negative durations falling back once; power-mode validation; one warning for an explicit non-loopback bind; and the other Review Focus conflicting-env cases.

- [ ] **A2 — Verify RED**

Run: `python -m pytest -q -p no:cacheprovider --basetemp=C:\Projects\seawatch\.swtmp tests/unit/test_live_config.py tests/unit/test_resilience_contracts.py`

Expected: import/collection failure because `config.py` and `resilience.py` do not exist.

- [ ] **A3 — Implement the pure contracts**

Implement only the declared enums/dataclasses and `LiveRuntimeConfig.from_env`; accept an injected mapping, never read/log secrets inside value objects, and expose warnings as a returned tuple/list for the caller to log once.

- [ ] **A4 — Verify GREEN and Cloud regression**

Run the focused command from A2, then `python -m pytest -q -p no:cacheprovider --basetemp=C:\Projects\seawatch\.swtmp tests/unit/test_live_ais.py`.

Expected: all pass; existing Cloud tests unchanged.

- [ ] **A5 — Commit**

Commit message: `feat: add resilience runtime contracts`

Expected behavior: pure validated contracts exist; deployed behavior is byte-for-byte unchanged.

## Slice B — Explicit Cloud-store ownership

**Files:**
- Create: `apps/api/seawatch/live/runtime.py`
- Create: `tests/unit/test_live_runtime.py`
- Modify: `apps/api/seawatch/live/__init__.py`
- Modify: `apps/api/seawatch/api/live.py`
- Modify: `apps/api/seawatch/main.py`
- Test unchanged: `tests/unit/test_live_ais.py`

**Interfaces:**
- Produce `CloudLiveState(store: LiveVesselStore, consumer: AisIngestConsumer)`.
- Produce `LiveRuntime.cloud`, `get_live_runtime() -> LiveRuntime`, and `reset_live_runtime() -> None`.
- Keep compatibility aliases `get_store()`, `get_consumer()`, and `reset_live_state()` returning/resetting the Cloud-owned objects.

**Risk / rollback:** Medium: singleton/lifespan wiring can silently duplicate consumers. Roll back this slice if object-identity or existing API tests differ.

**Independent commit:** Yes, only after the hard gate.

- [ ] **B1 — Write failing ownership/compatibility tests**

Assert one process-wide Cloud store/consumer; compatibility getters return the same objects; reset replaces both; startup starts exactly the existing consumer only when `SEAWATCH_LIVE_INGEST=true`; `/live/health`, `/live/vessels`, and track response shapes match pre-slice fixtures.

- [ ] **B2 — Verify RED**

Run: `python -m pytest -q -p no:cacheprovider --basetemp=C:\Projects\seawatch\.swtmp tests/unit/test_live_runtime.py tests/unit/test_live_ais.py`

Expected: failure because explicit `CloudLiveState`/`LiveRuntime` do not exist.

- [ ] **B3 — Migrate ownership without changing behavior**

Move singleton construction into `runtime.py`; keep `OpenWatersProvider`, `AisIngestConsumer`, store settings, startup flag, routes, fields, attribution, and exception behavior unchanged. Make `__init__.py` re-export compatibility functions.

- [ ] **B4 — Verify GREEN with focused Cloud tests**

Run B2 command. Expected: all current live tests and new ownership tests pass.

- [ ] **B5 — HARD GATE: full Cloud regression**

Run: `python -m pytest -q -p no:cacheprovider --basetemp=C:\Projects\seawatch\.swtmp`

GO only if the complete pre-Edge suite passes and no existing `/live/*` assertion changed. STOP on any regression; revert Slice B rather than adapting Cloud behavior.

- [ ] **B6 — Commit**

Commit message: `refactor: make cloud live state ownership explicit`

Expected behavior: Cloud Live is unchanged, now explicitly owned and ready for additional sources.

## Slice C — Opaque identity and Cloud-only active view

**Files:**
- Create: `apps/api/seawatch/live/identity.py`
- Create: `apps/api/seawatch/live/active_view.py`
- Create: `tests/unit/test_live_identity.py`
- Create: `tests/unit/test_active_vessel_view.py`
- Modify: `apps/api/seawatch/live/runtime.py`
- Modify: `apps/api/seawatch/live/schema.py`
- Modify: `apps/api/seawatch/api/live.py`
- Modify: `tests/unit/test_live_ais.py`

**Interfaces:**
- Produce `IdentityBinding(public_id, source_key, source_name, mmsi)` internal-only and `VesselIdentityRegistry.public_id_for(observation) -> str`, `.resolve(public_id) -> IdentityBinding | None`, `.expire(public_id) -> None`.
- Produce `PublicVesselObservation(public_id, observation, origin, display_state, active_source, coverage)` and `ActiveTrack(public_id, source_name, points)`.
- Produce Cloud-only `ActiveVesselView(cloud_store, identity_registry, *, monotonic=time.monotonic)`, `.snapshot(bbox=None, now=None) -> list[PublicVesselObservation]`, and `.track(public_id) -> ActiveTrack | None`.

**Risk / rollback:** High: identity changes selection/track URLs and privacy. Roll back API routing to Cloud store if any privacy or compatibility assertion fails.

**Independent commit:** Yes, after privacy hard gate.

- [ ] **C1 — Write failing identity tests**

Assert HMAC-SHA256 IDs use `SEAWATCH_IDENTITY_KEY`, start with `v_`, remain stable for the same valid MMSI, differ across keys/MMSIs, cannot contain MMSI, and random process-local IDs are used when MMSI is absent. Assert collision checking and expired reverse bindings.

- [ ] **C2 — Write failing Cloud-only view/API tests**

Assert current Cloud features/track coordinates remain, `provider_id` and GeoJSON `id` are opaque, provenance is `cloud/live`, and track lookup resolves through the Cloud binding. Scan serialized `/live/vessels` and track output for `mmsi`, `imo`, `callsign`, known numeric identities, and raw source IDs.

- [ ] **C3 — Verify RED**

Run: `python -m pytest -q -p no:cacheprovider --basetemp=C:\Projects\seawatch\.swtmp tests/unit/test_live_identity.py tests/unit/test_active_vessel_view.py tests/unit/test_live_ais.py`

Expected: imports fail because registry/view contracts do not exist.

- [ ] **C4 — Implement keyed identity and Cloud-only facade**

Use HMAC-SHA256 with a configured backend key and collision-checked truncated URL-safe token; generate an unlogged process-local random key if absent. Route Cloud-only API reads through `ActiveVesselView` while preserving existing field types and routes additively.

- [ ] **C5 — Verify GREEN**

Run C3 command and the full backend suite. Expected: Cloud functionality passes with opaque public IDs.

- [ ] **C6 — HARD GATE: privacy boundary**

Run the dedicated serialized-response scan and `rg -n "mmsi|imo|callsign" apps/web/src` to confirm no frontend contract exposes those fields. GO only when known source identifiers are absent from every public payload. STOP and restore direct Cloud routing if not.

- [ ] **C7 — Commit**

Commit message: `feat: add opaque live vessel identities`

Expected behavior: the application is still Cloud-only, but all public IDs and tracks pass through an explicit privacy/provenance seam.

## Slice D — Pure Edge AIS decoder

**Files:**
- Create: `apps/api/seawatch/live/edge_ais.py`
- Create: `tests/unit/test_edge_ais.py`
- Create: `tests/fixtures/ais/edge_nmea.txt`
- Modify: `requirements.txt` (`pyais==3.2.3` only)

**Interfaces:**
- Produce `EdgeDecodeResult(observations, accepted_frames, rejected_frames, pending_fragments)`.
- Produce `EdgeAisDecoder(max_line_bytes=1024, fragment_ttl_seconds=15.0, monotonic=time.monotonic)`.
- Produce `EdgeAisDecoder.feed_line(line: bytes, *, received_at: datetime) -> EdgeDecodeResult` and `.expire_fragments() -> int`.
- Output only normalized `LiveVesselObservation(source="edge_ais", synthesized=False, mmsi=<internal>)` for AIS position types 1/2/3/18/19/27.

**Risk / rollback:** Medium-high: malformed/multipart protocol handling can corrupt identity or freshness. Roll back the dependency and isolated decoder files; no runtime consumes them yet.

**Independent commit:** Yes; decoder is pure and not wired to sockets/startup.

- [ ] **D1 — Write failing recorded-fixture tests before adding the dependency**

Cover one valid Class A position, one Class B position, valid two-part assembly, checksum rejection, missing/out-of-order/duplicate fragments, reused sequence/channel isolation, unsupported static-only message, 1024-byte limit, coordinate/SOG/COG/heading sentinels, tag-block timestamp, receive-time fallback, fragment expiry, and bounded assembly count.

- [ ] **D2 — Verify RED**

Run: `python -m pytest -q -p no:cacheprovider --basetemp=C:\Projects\seawatch\.swtmp tests/unit/test_edge_ais.py`

Expected: import failure because `EdgeAisDecoder` does not exist.

- [ ] **D3 — Add and validate `pyais==3.2.3`**

Add the exact runtime pin to `requirements.txt`, install it in the active environment, and record `python -c "import pyais; print(pyais.__version__)"`. If Windows/Python 3.12 installation or API compatibility fails, STOP and revisit the dependency decision; do not write AIS bit decoding.

- [ ] **D4 — Implement minimal pure decoding**

Use `pyais` for NMEA checksum/payload and AIS field decoding. SeaWatch owns line bounds, multipart keys/expiry, supported-position filtering, sentinels, timestamps, and normalization. Never log raw payloads or identities.

- [ ] **D5 — Verify GREEN and dependency isolation**

Run D2, `tests/unit/test_live_ais.py`, then the full backend command. Expected: all pass without sockets or Internet.

- [ ] **D6 — Commit**

Commit message: `feat: decode local AIS NMEA observations`

Expected behavior: fixture NMEA normalizes deterministically; production startup remains Cloud-only.

## Slice E — Edge UDP/replay lifecycle and health

**Files:**
- Create: `apps/api/seawatch/live/edge_ingest.py`
- Create: `apps/api/seawatch/api/resilience.py`
- Create: `tests/unit/test_edge_ingest.py`
- Create: `tests/unit/test_edge_api.py`
- Modify: `apps/api/seawatch/live/runtime.py`
- Modify: `apps/api/seawatch/live/__init__.py`
- Modify: `apps/api/seawatch/main.py`
- Modify: `tests/unit/test_live_runtime.py`

**Interfaces:**
- Produce mutable `EdgeIngestHealth(receiver_active, receiver_detected, input_kind, bind_host, bind_port, last_nmea_at, last_valid_ais_at, received_messages, decoded_messages, rejected_messages, last_error)` with `snapshot(store, now) -> dict`.
- Produce `EdgeAisConsumer(decoder, store, config, *, monotonic, sleep)` with non-blocking `start()`, async `stop()`, `handle_datagram(data, addr)`, and async replay loop.
- Extend `LiveRuntime.edge` with a completely separate `LiveVesselStore` and `EdgeAisConsumer`.
- Add `GET /edge/health`; it is read-only and returns inactive health when Edge is disabled.

**Risk / rollback:** High: lifecycle mistakes can bind unexpectedly, leak tasks, or disturb FastAPI shutdown. Edge remains disabled by default; roll back new lifespan wiring while retaining the pure decoder if the gate fails.

**Independent commit:** Yes, because active `/live/*` still reads Cloud only.

- [ ] **E1 — Write failing UDP/framing/health tests**

Call the datagram handler directly with one/multiple newline-delimited frames, CRLF, blank lines, non-loopback sender metadata, oversized datagrams, invalid-only traffic, and valid positions. Assert received/decoded/rejected counts, last-NMEA versus last-valid time, separate Edge track growth, and no freshness update for invalid input.

- [ ] **E2 — Write failing replay/lifecycle/API tests**

Assert replay requires both enable flag and file; a path alone does nothing; UDP/replay are mutually exclusive; replay uses the same decoder/store, timing is injected/cancellable, and source/input kind is replay. Assert disabled Edge and failed UDP bind leave Cloud startup and `/live/*` working, expose one bounded error, and create no hot retry/noisy log loop.

- [ ] **E3 — Verify RED**

Run: `python -m pytest -q -p no:cacheprovider --basetemp=C:\Projects\seawatch\.swtmp tests/unit/test_edge_ingest.py tests/unit/test_edge_api.py tests/unit/test_live_runtime.py`

Expected: imports/routes fail because Edge lifecycle does not exist.

- [ ] **E4 — Implement UDP/replay lifecycle behind flags**

Use `asyncio.create_datagram_endpoint` bound to configured `127.0.0.1:10110`; split bounded lines and delegate to the decoder. Build replay as a cancellable file loop with injected sleep and replace normalized attribution with `source="edge_replay"`/replay input kind before the Edge-store write. Start Edge independently in FastAPI lifespan only when explicitly enabled; catch bind/file/decoder errors into health without blocking Cloud.

- [ ] **E5 — Verify GREEN**

Run E3, `tests/unit/test_live_ais.py`, and the full backend command. Expected: offline tests pass without opening a real socket or fixture outside the repo.

- [ ] **E6 — HARD GATE: hardware absence and Cloud isolation**

Run the app lifecycle tests with no SDR, no AIS-catcher, Edge disabled, Edge enabled with no messages, and simulated bind failure. GO only if FastAPI starts, Cloud consumer identity/behavior is unchanged, `/live/*` passes, `/edge/health` says inactive/not detected, and logs are bounded. STOP and remove Edge lifespan activation otherwise.

- [ ] **E7 — Commit**

Commit message: `feat: add local edge AIS ingest lifecycle`

Expected behavior: optional UDP/replay fills only the Edge store and reports independent health; it cannot yet replace Cloud API data.

## Slice F — Resilience mode manager and hysteresis

**Files:**
- Create: `tests/unit/test_resilience_manager.py`
- Modify: `apps/api/seawatch/live/resilience.py`
- Modify: `apps/api/seawatch/live/runtime.py`

**Interfaces:**
- Produce `ResilienceModeManager(config: LiveRuntimeConfig, *, monotonic: Callable[[], float])`.
- Produce `.evaluate(cloud: SourceHealthSnapshot, edge: SourceHealthSnapshot, *, offline_demo: bool = False) -> ResilienceStatus` and read-only `.current_mode`.
- Preserve internal `cloud_recovery_started_at: float | None`; never use wall-clock subtraction for hysteresis.

**Risk / rollback:** High: a state bug can flap or mislabel data. The manager remains unconnected to `/live/*` until Slice G, so rollback is isolated.

**Independent commit:** Yes; pure state machine only.

- [ ] **F1 — Write failing deterministic state tests**

Cover Cloud fresh → `CLOUD_LIVE`; Cloud stale + real Edge fresh → `EDGE_LIVE`; Cloud stale + replay fresh → `EDGE_REPLAY`; both stale → `NO_LIVE_SOURCE`; explicit demo → `OFFLINE_DEMO`; no automatic demo; fresh Edge never displaces fresh Cloud; exactly 30-second boundaries; 20-second continuous recovery; interrupted recovery reset; Edge stales during recovery; and wall timestamps absent.

- [ ] **F2 — Add Review Focus clock tests**

With a fake monotonic clock, test decreasing time, frozen time, and large forward jumps. Assert non-negative ages, no premature recovery, and at most one transition event per real state change.

- [ ] **F3 — Verify RED**

Run: `python -m pytest -q -p no:cacheprovider --basetemp=C:\Projects\seawatch\.swtmp tests/unit/test_resilience_manager.py`

Expected: failure because `ResilienceModeManager` does not exist.

- [ ] **F4 — Implement the state machine minimally**

Compute source freshness from monotonic last-message values and config; keep Cloud primary; distinguish UDP from replay; preserve Edge mode until uninterrupted Cloud recovery completes; emit status/coverage/simulated fields without mutating either store.

- [ ] **F5 — Verify GREEN and backend regression**

Run F3 and the full backend command. Expected: deterministic state tests and all prior Cloud/Edge tests pass.

- [ ] **F6 — Commit**

Commit message: `feat: add resilient live source mode manager`

Expected behavior: the real manager is testable but does not yet alter public active data.

## Slice G — Active failover API and provenance

**Files:**
- Create: `tests/unit/test_live_failover_api.py`
- Modify: `apps/api/seawatch/live/active_view.py`
- Modify: `apps/api/seawatch/live/identity.py`
- Modify: `apps/api/seawatch/live/runtime.py`
- Modify: `apps/api/seawatch/api/live.py`
- Modify: `apps/api/seawatch/api/resilience.py`
- Modify: `tests/unit/test_active_vessel_view.py`
- Modify: `tests/unit/test_live_ais.py`

**Interfaces:**
- Extend `ActiveVesselView.snapshot(status, bbox=None, now=None) -> list[PublicVesselObservation]` to select active store and retain the prior snapshot for `300s` using its injected monotonic clock.
- Extend `IdentityBinding` with `source_name`/`source_key` ownership and allow one public identity to hold separate Cloud/Edge bindings only after a valid same-MMSI match.
- `ActiveVesselView.track(public_id) -> ActiveTrack | None` resolves the provenance of the currently displayed active/cached feature, independent of current mode.
- Add `GET /resilience/status`; extend `/live/health` and `/live/vessels` additively with mode, coverage, simulated, origin, display state, and active-source fields.

**Risk / rollback:** Highest backend risk: it changes which store public routes read and combines identity, cache, health, and tracks. Roll back route delegation to the Slice C Cloud-only facade if any gate fails; do not alter stores to compensate.

**Independent commit:** Yes, only after the hard gate.

- [ ] **G1 — Write failing active-source/cache tests**

Cover Cloud/Edge/Replay/no-source selection, 300-second retention/expiry, `live` versus `cached` versus `stale`, original observation origin, active-source flag, coverage, source-specific counts, bbox filtering after selection, and no cached record counted as a local vessel.

- [ ] **G2 — Write failing dedupe/track tests**

Assert identical valid MMSI maps to one public identity and prefers the freshest observation allowed by active mode; absent/invalid/uncertain MMSI never merges. Assert active Cloud → Cloud track, active Edge → Edge track, cached Cloud during `EDGE_LIVE` → Cloud track, cached Edge during `CLOUD_LIVE` → Edge track, no track splicing, and expired cached binding → `404`.

- [ ] **G3 — Write failing API/status compatibility tests**

Assert `/resilience/status` nested Cloud/Edge health and power fields; `/live/health` retains every previous key; `/live/vessels` retains GeoJSON/current properties plus provenance; no-source returns labeled cache then empty; replay is simulated; privacy scan remains clean.

- [ ] **G4 — Verify RED**

Run: `python -m pytest -q -p no:cacheprovider --basetemp=C:\Projects\seawatch\.swtmp tests/unit/test_active_vessel_view.py tests/unit/test_live_failover_api.py tests/unit/test_live_ais.py`

Expected: failures because the view still operates Cloud-only and status route is incomplete.

- [ ] **G5 — Implement active failover facade**

Evaluate the real manager from independent runtime health, snapshot the selected store, retain prior records as immutable provenance-labeled cache, merge only exact valid MMSI bindings, and route tracks through the displayed record’s source binding. Keep endpoint fields additive and attribution source-aware.

- [ ] **G6 — Verify GREEN with focused failover tests**

Run G4 plus `tests/unit/test_resilience_manager.py tests/unit/test_edge_ingest.py tests/unit/test_edge_api.py`.

Expected: all failover, hysteresis, health, cache, dedupe, and track ownership assertions pass.

- [ ] **G7 — HARD GATE: backend resilience contract**

Run the full backend command twice to catch leaked singleton/task state. GO only if both runs pass with no Internet/hardware, serialized payloads remain private, and all provenance/hysteresis cases pass. STOP and return `/live/*` to Cloud-only Slice C behavior on failure.

- [ ] **G8 — Commit**

Commit message: `feat: expose active resilient AIS view`

Expected behavior: backend failover is complete and honest before any frontend relies on it.

## Slice H — Frontend resilience UX

**Files:**
- Create: `apps/web/src/lib/resilience.ts`
- Create: `apps/web/src/lib/resilience.test.ts`
- Create: `apps/web/src/components/ResilienceBanner.tsx`
- Create: `apps/web/src/components/ResilienceBanner.test.tsx`
- Modify: `apps/web/src/api/live.ts`
- Modify: `apps/web/src/lib/liveStatus.ts`
- Modify: `apps/web/src/lib/liveStatus.test.ts`
- Modify: `apps/web/src/lib/integrity.ts`
- Modify: `apps/web/src/components/AppHeader.tsx`
- Modify: `apps/web/src/components/AppHeader.test.tsx`
- Modify: `apps/web/src/components/MapCanvas.tsx`
- Modify: `apps/web/src/components/MapCanvas.test.tsx`
- Modify: `apps/web/src/components/VesselPanel.tsx`
- Modify: `apps/web/src/pages/LiveDashboard.tsx`
- Modify: `apps/web/src/pages/LiveDashboard.test.tsx`
- Modify: `apps/web/src/i18n/dictionaries.ts`
- Modify: `apps/web/src/i18n/i18n.test.tsx`
- Modify: `apps/web/src/styles.css`

**Interfaces:**
- Add `OperatingMode`, `CoverageKind`, `ObservationOrigin`, `DisplayState`, `ResilienceStatus`, and additive vessel properties matching Slice G wire values.
- Produce `modePresentation(status, t)`, `transitionEvent(previous, next)`, and `vesselIntegrity(feature)` pure helpers.
- `AppHeader` accepts explicit mode presentation; `ResilienceBanner` accepts current status plus previous mode and emits one non-blocking transition.

**Risk / rollback:** Medium-high: polling/state changes can disturb the polished map/selection/follow UX. Components remain additive; roll back presentation wiring without changing backend.

**Independent commit:** Yes.

- [ ] **H1 — Write failing pure presentation/i18n tests**

Assert exact Cloud/Edge/Replay/no-source/demo labels in zh-Hant and English, `taiwan_wide_network_feed` versus `local_rf`, mandatory local-antenna explanation, replay-not-live-RF text, External Power/Battery-UPS copy, and no mojibake replacement characters.

- [ ] **H2 — Write failing interaction/render tests**

Assert a Cloud→Edge banner appears once without unmounting MapCanvas, Cloud restoration appears once, simulated transition is prefixed, cached/stale vessels receive distinct properties/classes, existing selection/follow/search/presets persist, and no-source keeps cached markers visible.

- [ ] **H3 — Verify RED**

Run from `apps/web`: `npm test -- src/lib/resilience.test.ts src/components/ResilienceBanner.test.tsx src/pages/LiveDashboard.test.tsx`

Expected: missing modules/types and mode labels.

- [ ] **H4 — Implement API types and pure mode derivation**

Consume backend mode/provenance as authoritative; remove heuristics that could call cached Cloud data live. Keep explicit Vite Offline Demo configuration separate from automatic status.

- [ ] **H5 — Implement polished additive UX**

Update the compact header, banner, status cards/panel, marker styling, and bilingual dictionary. Preserve existing FR24-style layout, polling, MapLibre source, selection, follow, interpolation labeling, and responsive drawer.

- [ ] **H6 — Verify GREEN, full frontend, and build**

Run focused H3, then from `apps/web`: `npm test` and `npm run build`.

Expected: all frontend tests pass and TypeScript/Vite build exits 0.

- [ ] **H7 — Commit**

Commit message: `feat: add honest resilience mode UX`

Expected behavior: users can distinguish Cloud, RF Edge, replay, no source, demo, cached/stale data, local coverage, and power requirements without losing current interactions.

## Slice I — Optional local frontend serving

**Files:**
- Create: `apps/api/seawatch/web/__init__.py`
- Create: `apps/api/seawatch/web/serving.py`
- Create: `tests/unit/test_web_serving.py`
- Modify: `apps/api/seawatch/main.py`
- Modify: `apps/api/seawatch/live/config.py`
- Modify: `tests/unit/test_live_config.py`
- Modify: `apps/web/src/api/client.ts`
- Modify: `apps/web/src/api/client.test.ts`
- Modify: `apps/web/.env.example`

**Interfaces:**
- Produce `configure_local_web(app: FastAPI, config: LiveRuntimeConfig) -> None`.
- With `SEAWATCH_SERVE_WEB=false`, register no root/assets/SPA routes.
- With it true, serve validated `SEAWATCH_WEB_DIST` assets, local `/`, and a last-registered SPA fallback; missing dist returns root `503` while APIs remain available.
- Produce pure `resolveApiBaseUrl(explicitBaseUrl: string | undefined, isDevelopment: boolean) -> string`; `getBaseUrl()` delegates using Vite env/mode.
- API-base precedence is exact: a non-empty explicit `VITE_API_BASE_URL` always wins and has trailing slashes removed; no explicit value returns `http://localhost:8000` only when `import.meta.env.DEV` is true; every production build otherwise returns `""`, yielding relative same-origin requests.

**Risk / rollback:** High deployment risk: catch-all routing can shadow APIs or change Render. The feature defaults off; rollback is removal of one conditional registration call.

**Independent commit:** Yes, after deployment-safety gate.

- [ ] **I1 — Write failing default/enabled/static tests**

Using `tmp_path`, assert disabled default leaves `/` behavior unchanged; enabled serves index and hashed asset; missing/invalid dist logs once and root returns local `503`; assets reject traversal; MIME/cache behavior is appropriate.

- [ ] **I2 — Write failing route-precedence/SPA tests**

With serving enabled, assert `/live/health`, `/live/vessels`, `/resilience/status`, `/edge/health`, `/offline/taiwan.pmtiles`, and `/health` are never captured; `/vessel/example` returns local index; nonexistent asset returns `404`, not index.

- [ ] **I3 — Write failing frontend API-base tests**

In `client.test.ts`, test the pure resolver and fetch URLs for: explicit `https://seawatch-bgsi.onrender.com/` in production/dev → trimmed Render URL; no explicit value in production → `""` and `/health`/`/live/*` relative requests; no explicit value in development → `http://localhost:8000`; empty/whitespace explicit value → mode fallback. Update `.env.example` so the cloud/development override is documented but commented out and Edge requires no `.env`.

- [ ] **I4 — Verify RED**

Run backend: `python -m pytest -q -p no:cacheprovider --basetemp=C:\Projects\seawatch\.swtmp tests/unit/test_web_serving.py tests/unit/test_live_config.py`.

Run from `apps/web`: `npm test -- src/api/client.test.ts`.

Expected: backend serving behavior is missing and the production-without-env client still returns `http://localhost:8000` instead of same origin.

- [ ] **I5 — Implement optional serving seam**

Use Starlette/FastAPI static responses already installed. Validate resolved dist path, register API routers first and SPA fallback last, distinguish extension-bearing asset paths from client routes, and never redirect to Vercel or another origin.

- [ ] **I6 — Implement the API-base selection contract**

Extract the pure resolver, keep the explicit Vercel→Render override, restrict `http://localhost:8000` to Vite development, and use empty-string relative paths for production without an override. Do not add an Edge `.env` or embed the Render URL in code.

- [ ] **I7 — Verify GREEN and full regressions**

Run I4 commands, the full backend command, `npm test`, and `npm run build`. Point a test config at `apps/web/dist` for a local TestClient smoke check.

- [ ] **I8 — HARD GATE: deployment and same-origin isolation**

With all new backend flags absent, assert application route/OpenAPI sets and lifespan match pre-slice behavior and no dist lookup occurs. With `SEAWATCH_SERVE_WEB=true`, serve the production build at `http://127.0.0.1:8000`, assert its `/live/*`, `/edge/*`, `/resilience/*`, and `/health` calls stay on exact origin `http://127.0.0.1:8000`, require no CORS, and prove API precedence plus SPA fallback. Fail on `http://localhost:8000`, Vercel, Render, or any cross-origin API request.

With `SEAWATCH_SERVE_WEB=false`, verify Render behavior is unchanged and a Vercel production build with explicit `VITE_API_BASE_URL=https://seawatch-bgsi.onrender.com` still targets Render. GO only when both deployment paths pass. STOP and remove serving/client changes otherwise.

- [ ] **I9 — Commit**

Commit message: `feat: optionally serve the local SeaWatch web app`

Expected behavior: Cloud deployment remains unchanged; an Edge operator can serve a prepared local UI whose relative API requests remain on the exact page origin.

## Slice J — PMTiles and zero-network emergency map

**Files:**
- Create: `apps/web/src/config/offlineMap.ts`
- Create: `apps/web/src/config/offlineMap.test.ts`
- Create: `apps/web/src/assets/taiwan-emergency.geojson`
- Create: `apps/web/src/assets/README.md`
- Create: `apps/web/playwright.config.ts`
- Create: `apps/web/e2e/offline-edge.spec.ts`
- Modify: `apps/web/package.json` (`pmtiles@4.5.0`, `@playwright/test@1.63.0` only)
- Modify: `apps/web/package-lock.json`
- Modify: `apps/web/src/config/taiwanMap.ts`
- Modify: `apps/web/src/config/taiwanMap.test.ts`
- Modify: `apps/web/src/components/MapCanvas.tsx`
- Modify: `apps/web/src/components/MapCanvas.test.tsx`
- Modify: `apps/api/seawatch/web/serving.py`
- Modify: `tests/unit/test_web_serving.py`
- Modify: `apps/api/seawatch/live/config.py`
- Modify: `tests/unit/test_live_config.py`

**Interfaces:**
- Produce `registerPmtilesProtocol()`, `pmtilesStyle()`, `emergencyStyle()`, and `selectOfflineBasemap(mode, onlineFailureState)` in `offlineMap.ts`.
- Browser archive URL is constant `/offline/taiwan.pmtiles`; no `VITE_*` path exists.
- Backend maps `SEAWATCH_PMTILES_FILE` to `GET/HEAD /offline/taiwan.pmtiles` with standard byte-range semantics.
- `MapCanvas` basemap state is `nlsc -> pmtiles -> emergency`; a failed NLSC/PMTiles source is not retried until reload or explicit operator action.

**Risk / rollback:** Highest frontend/operations risk: MapLibre style/protocol and HTTP ranges can blank the map. Emergency style is the safe terminal state; rollback PMTiles while retaining emergency map if needed.

**Independent commit:** Yes, after the zero-network hard gate.

- [ ] **J1 — Write failing backend PMTiles route tests**

Use a temporary byte file, not a committed archive. Assert runtime filesystem relocation without rebuild; GET/HEAD; `bytes=0-15`, open-ended, suffix, unsatisfiable, malformed, and multiple-range behavior; correct `206/416`, `Content-Range`, length, and missing-file `404`; configured path is a regular file and no traversal is accepted.

- [ ] **J2 — Write failing frontend style/failover tests**

Assert protocol registration occurs once before Map construction; PMTiles URL is fixed and relative; emergency style contains only bundled GeoJSON/local values and no `http`, glyph, sprite, remote font, or tile URL; NLSC errors transition once to PMTiles, missing PMTiles transitions once to emergency, and Edge/no-source mode bypasses repeated NLSC attempts.

- [ ] **J3 — Write failing real-browser test**

Build without `VITE_API_BASE_URL`, launch local FastAPI on `127.0.0.1:8000` with web serving on and PMTiles intentionally absent, and require the page URL to be `http://127.0.0.1:8000`. Intercept every application/API/map request and fail unless its origin is exactly `http://127.0.0.1:8000` (allow another loopback representation only for an explicitly documented test-harness control channel). Assert app header, emergency map canvas, ports/Taiwan context, `/live/*`, and resilience UI render. Explicitly fail on `localhost:8000`, Vercel, Render, NLSC, CDN, or any other origin.

- [ ] **J4 — Verify RED before adding packages**

Run backend focused tests and from `apps/web` run `npm test -- src/config/offlineMap.test.ts src/components/MapCanvas.test.tsx`.

Expected: missing PMTiles route/module/protocol behavior. The Playwright command is expected unavailable before its dev dependency is added.

- [ ] **J5 — Add pinned frontend dependencies and preinstall Chromium**

Add only `pmtiles@4.5.0` runtime and `@playwright/test@1.63.0` dev dependency; update lockfile. Run `npx playwright install chromium` while Internet is available before the offline drill. Browser installation is provisioning, never an outage-time step.

- [ ] **J6 — Implement range route and map hierarchy**

Serve the configured file with validated range semantics. Bundle/register `Protocol`; add the public-domain Natural Earth-derived simplified Taiwan outline plus attribution; build a style with system/bundled labels and existing local commercial-port data; preserve vessel overlays across `setStyle` transitions; latch dead sources for the session.

- [ ] **J7 — Verify GREEN with unit suites and build**

Run the focused backend tests, full backend command, then `npm test` and `npm run build` from `apps/web`.

- [ ] **J8 — HARD GATE: disconnected browser**

Run from `apps/web`: `npx playwright test e2e/offline-edge.spec.ts --project=chromium` with outbound requests blocked by the test and PMTiles absent.

GO only if the built `127.0.0.1:8000` UI, emergency map, and API-backed status render; every observed application/API/map request uses the exact page origin; and localhost, Vercel, Render, NLSC, remote fonts/glyphs/sprites, CDNs, and every other origin are absent. STOP and fix API-base/asset/style references before proceeding.

- [ ] **J9 — Commit**

Commit message: `feat: add fully offline resilient basemap`

Expected behavior: normal Cloud begins with NLSC; disconnected Edge uses local PMTiles when installed and guaranteed emergency geography otherwise.

## Slice K — Simulation-only failure drill

**Files:**
- Create: `scripts/resilience_drill.py`
- Create: `tests/integration/test_resilience_drill.py`
- Modify: none in production application

**Interfaces:**
- Produce CLI `python scripts/resilience_drill.py --enable-simulation [--fixture PATH] [--json-output PATH]`.
- Import `ResilienceModeManager`, `EdgeAisDecoder`, and stores from production modules; use injected clock/health only.
- Exit nonzero without `--enable-simulation`; every log/record contains `SIMULATED`/`simulated=true`.

**Risk / rollback:** Medium: a drill could be mistaken for production control. It has no server endpoint and no process-global runtime mutation; delete script/test to roll back.

**Independent commit:** Yes.

- [ ] **K1 — Write failing CLI/sequence tests**

Assert refusal without flag and the exact seven stages: Cloud, outage, explicit replay, `EDGE_REPLAY`, Cloud restored but held, recovery elapsed, `CLOUD_LIVE`. Assert it uses the configured recovery value, labels every record simulated, and never emits `EDGE_LIVE` for replay.

- [ ] **K2 — Verify RED**

Run: `python -m pytest -q -p no:cacheprovider --basetemp=C:\Projects\seawatch\.swtmp tests/integration/test_resilience_drill.py`

Expected: script missing.

- [ ] **K3 — Implement the thin CLI**

Use the real manager and optional real fixture decoder/store; advance a deterministic fake monotonic clock. Do not import or mutate `get_live_runtime`, bind sockets, add a production endpoint, or disable Windows networking.

- [ ] **K4 — Verify GREEN and manual transcript**

Run K2 and `python scripts/resilience_drill.py --enable-simulation`.

Expected: test passes and transcript shows the seven `SIMULATED` stages with recovery delay.

- [ ] **K5 — Commit**

Commit message: `feat: add simulated resilience failure drill`

Expected behavior: an operator can demonstrate policy deterministically without touching live sources.

## Slice L — Runbooks, measurements, and final verification

**Files:**
- Create: `scripts/measure_edge_resilience.py`
- Create: `tests/unit/test_resilience_measurement.py`
- Create: `apps/web/e2e/map-performance.spec.ts`
- Create: `docs/edge-ais-runbook.md`
- Create: `docs/offline-map.md`
- Create: `docs/offline-startup-runbook.md`
- Create: `docs/phase8-edge-resilience-report.md`
- Modify: `README.md`
- Modify: `.gitignore` (ignore local PMTiles, Playwright output, and measurement scratch only)

**Interfaces:**
- Produce CLI `python scripts/measure_edge_resilience.py --fixture PATH --iterations N --output PATH` with environment metadata and median/p95/max for decode, store update, ingest rate, and `/live/vessels`.
- Produce Playwright performance scenario that records MapLibre GeoJSON update samples using browser Performance API without claiming network/render metrics it does not measure.
- Runbooks specify Windows laptop + RTL-SDR + VHF/AIS antenna + AIS-catcher + localhost FastAPI, plus battery/UPS and local-only coverage limitations.

**Risk / rollback:** Medium documentation/measurement credibility risk. Measurements must be reproducible and clearly machine-specific; omit rather than invent unavailable values.

**Independent commit:** Yes; this is the final Phase 8 commit after all gates.

- [ ] **L1 — Write failing measurement-contract tests**

Assert fixture-only execution, warm-up exclusion, sample count, nanosecond monotonic timing, percentile calculation, machine/package metadata, privacy scan, and refusal to write misleading output when zero valid observations decode.

- [ ] **L2 — Verify RED**

Run: `python -m pytest -q -p no:cacheprovider --basetemp=C:\Projects\seawatch\.swtmp tests/unit/test_resilience_measurement.py`

Expected: measurement module/script missing.

- [ ] **L3 — Implement backend and frontend measurement harnesses**

Keep measurement code outside request hot paths except optional bounded counters. Use the committed small fixture and local TestClient; frontend scenario uses generated anonymous features and browser performance marks. Write output to ignored scratch, then copy only aggregate results into the report.

- [ ] **L4 — Write exact Windows-first runbooks**

Document AIS-catcher command shape, `127.0.0.1:10110`, env flags, PMTiles installation/runtime path, battery/UPS, disconnect sequence, health/status checks, Edge local-antenna limitation, replay warning, troubleshooting, and no-SDR safe behavior. Make the build contracts explicit:

- Edge: ensure `VITE_API_BASE_URL` is unset, run `npm run build`, enable local serving, start FastAPI, and open `http://127.0.0.1:8000`; relative API URLs stay on that FastAPI process and no npm dev server is used.
- Public cloud: Vercel builds with explicit `VITE_API_BASE_URL=https://seawatch-bgsi.onrender.com`; local static serving remains disabled on Render.

- [ ] **L5 — Run measurements and record only observed results**

Run the backend harness with declared iterations and the Playwright map-performance scenario. Record hardware/software, sample size, warm-up, median, p95, max, and caveats in `docs/phase8-edge-resilience-report.md`. If a measurement cannot run, record it as not measured with the reason.

- [ ] **L6 — Verify GREEN with all automated suites**

Run:

```powershell
python -m pytest -q -p no:cacheprovider --basetemp=C:\Projects\seawatch\.swtmp
Set-Location apps/web
npm test
npm run build
npx playwright test e2e/offline-edge.spec.ts --project=chromium
Set-Location ../..
```

Expected: zero failures, no Internet/SDR/AIS-catcher/PMTiles/production secret required. The Playwright browser binary must already be provisioned.

- [ ] **L7 — Run final reality/privacy/repository checks**

Verify the report explicitly states Cloud broad Taiwan network coverage, Edge local VHF only, Offline Demo not live, and power requires battery/UPS. Scan public bundles/API fixtures for identity fields and remote emergency-style URLs. Run `git status --short`, `git diff --check`, and confirm no `.pmtiles`, secrets, raw AIS, Playwright reports, or scratch measurements are staged.

- [ ] **L8 — Commit**

Commit message: `feat: add resilient edge AIS failover mode`

Expected behavior: Phase 8 is documented, measured, reproducible, and passes every gate; no deployment is performed.

## Hard-Gate Summary

| Gate | Required evidence | Failure action |
|---|---|---|
| After B | Full backend suite; unchanged `/live/*` Cloud behavior | Revert explicit ownership migration; do not start identity work. |
| After C | Serialized public payload scan has no MMSI/IMO/callsign/raw IDs | Restore Cloud-only direct routing; fix identity seam. |
| After E | No hardware/receiver/bind failure cannot affect Cloud startup/API | Disable/remove Edge lifespan wiring. |
| After G | Failover, recovery hysteresis, cache provenance, dedupe, and track ownership pass twice | Return active API to Cloud-only facade; no frontend work. |
| After I | Static serving off by default; same-origin Edge API; explicit Vercel→Render URL; API/SPA precedence | Remove serving/client changes; do not add map file route. |
| After J | Outbound-blocked browser at `127.0.0.1:8000` renders shell/map and every app/API/map request is exact same-origin | Fix API base, bundle, style, or serving; no drill/docs completion. |

## Final Verification and Handoff

The implementation is complete only after all slice commits and gates pass,
the working tree contains no uncommitted implementation, and fresh full-suite,
build, browser, privacy, and `git diff --check` evidence is captured in the
Phase 8 report. Do not squash or rewrite earlier commits; preserve the approved
design and plan history.
