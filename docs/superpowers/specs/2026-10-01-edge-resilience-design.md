# SeaWatch Phase 8 Edge Resilience Design

**Status:** Approved architecture; design and planning only

**Date:** 2026-10-01

**Base:** `feat/fr24-ui-polish` at `35a057d`

## 1. Purpose and boundaries

Phase 8 keeps SeaWatch useful when the Internet AIS feed is unavailable. The
existing Open Waters WebSocket ingest remains the primary production path and
continues to provide broad, network-based Taiwan AIS coverage. A secondary
path receives decoded civilian AIS NMEA from AIS-catcher over localhost UDP.

The operating claims are deliberately narrow:

- **Cloud Live** provides broad network-based Taiwan AIS coverage.
- **Edge Live** shows only civilian AIS vessels receivable by the local VHF antenna.
- **Edge Replay** is recorded development data, never live RF reception.
- **Offline Demo** is prerecorded/sample data, not live data, and requires
  explicit configuration.
- **Power resilience** requires a laptop battery or UPS. SeaWatch makes no
  battery-runtime estimate and does not claim operation without power.

Included: local NMEA ingest, separate stores, hysteretic failover, honest
transition caching, replay, offline maps, a simulation-only drill, tests,
measurements, and Windows-first runbooks. Excluded: SDR control, hardware
purchasing, cloud deployment, Challenge #10 logistics, anomaly retraining,
military/radar tracking, operational deployments, and sensitive locations.

## 2. Selected architecture

The existing Open Waters consumer writes only to a cloud store. A new edge
consumer writes only to an edge store. `ResilienceModeManager` selects the
operating mode from independent health snapshots. `ActiveVesselView` supplies
the unchanged `/live/*` routes with active and explicitly cached observations.

A single multiplexed store is rejected because it would blur health, tracks,
and provenance. A persistent event bus/database is deferred because bounded
in-memory state satisfies Phase 8 without migration and locking complexity.

## 3. Component and module diagram

```text
INTERNET
Open Waters -> existing AisIngestConsumer -> Cloud LiveVesselStore -----+
                                                                        |
LOCAL RF                                                                v
RTL-SDR -> AIS-catcher -> UDP 127.0.0.1:10110 -> LocalNmeaAisProvider   |
                                                    |                   |
                                                    v                   |
                                           Edge LiveVesselStore --------+
                                                    |
                                                    v
                                         ResilienceModeManager
                                                    |
                                                    v
                                           ActiveVesselView
                                      + identity + transition cache
                                                    |
                     +------------------------------+----------------+
                     v                              v                v
                 /live/*                  /resilience/status   /edge/health
                     |
                     v
             React mode/provenance UI
                     |
                     v
       NLSC -> local PMTiles -> emergency local map
```

Planned modules:

| Module | Responsibility |
|---|---|
| `live/edge_ais.py` | Decode NMEA/AIS and normalize position reports. |
| `live/edge_ingest.py` | Own localhost UDP or replay, framing, counters, lifecycle. |
| `live/resilience.py` | Health contracts, state machine, monotonic hysteresis. |
| `live/identity.py` | Internal MMSI matching and keyed opaque public IDs. |
| `live/active_view.py` | Select active data, cache transitions, resolve tracks. |
| `api/resilience.py` | `/resilience/status` and `/edge/health`. |

The existing `open_waters.py` parsing and `AisIngestConsumer` WebSocket
behavior remain. Wiring changes only to give them the dedicated cloud store.

## 4. Source and store ownership

Cloud and Edge independently own observations, track histories, freshness,
message counts, source state, and errors. The active view reads snapshots; it
never moves records between stores.

| Data | Cloud owner | Edge owner | Active-view behavior |
|---|---|---|---|
| Observations | Cloud store | Edge store | Select by mode; never relabel. |
| Tracks | Cloud store | Edge store | Return selected store track; never splice. |
| Counters/times | Cloud consumer/store | Edge consumer/store | Report independently. |
| Connectivity | WebSocket consumer | UDP/replay consumer | Never infer one from the other. |
| Coverage | `taiwan_wide_network_feed` | `local_rf` | Return with mode/collection. |

An edge listener is `receiver_active` when its UDP or replay task starts.
Real RF is `receiver_detected` only after valid NMEA arrives recently. Merely
binding an empty UDP socket does not claim AIS-catcher or SDR presence.

## 5. Operating modes and state machine

Backend and frontend share five explicit states:

```text
CLOUD_LIVE
EDGE_LIVE
EDGE_REPLAY
NO_LIVE_SOURCE
OFFLINE_DEMO
```

`EDGE_REPLAY` is not a hidden subtype of Edge Live. `OFFLINE_DEMO` is entered
only through explicit demo configuration; neither is an automatic fallback.

```text
                           cloud fresh
             +----------------------------------+
             |                                  v
      NO_LIVE_SOURCE                       CLOUD_LIVE
             ^                                  |
             | both stale                       | cloud stale
             |                                  v
             +-------------------------- edge input fresh?
                                                / \
                                              no   yes
                                              |     |
                                              +   input kind
                                                   / \
                                                 UDP replay
                                                  |    |
                                                  v    v
                                            EDGE_LIVE EDGE_REPLAY
                                                  \    /
                           cloud continuously fresh for recovery interval
                                                     |
                                                     v
                                                CLOUD_LIVE

OFFLINE_DEMO is outside the automatic transitions.
```

Precedence is explicit Offline Demo, fresh cloud, fresh real Edge, explicitly
enabled fresh replay, then no live source. Fresh Edge never displaces healthy
Cloud.

## 6. Freshness and hysteresis

| Environment variable | Default | Meaning |
|---|---:|---|
| `SEAWATCH_CLOUD_STALE_SECONDS` | `30` | Cloud becomes stale without a position. |
| `SEAWATCH_EDGE_STALE_SECONDS` | `30` | Edge becomes stale without a decoded position. |
| `SEAWATCH_CLOUD_RECOVERY_SECONDS` | `20` | Continuous freshness before Edge-to-Cloud return. |

Invalid values fall back to defaults with one startup warning. UTC wall time is
kept for API timestamps; injected monotonic time drives elapsed freshness and
recovery intervals where practical.

```text
time -------------------------------------------------------------->
cloud: * * * *       [outage]                         * * * * * *
edge:              * * * * * * * * * * * * * * * * * * * * * *
mode:  CLOUD_LIVE    EDGE_LIVE                         EDGE_LIVE
                                                        |<--20s-->|
                                                        stable cloud
mode:                                                             CLOUD_LIVE
cache:              prior cloud fixes remain Cached/Stale only
```

The recovery delay applies after Edge operation to prevent flapping. If Edge
also becomes stale before cloud recovery completes, the mode becomes
`NO_LIVE_SOURCE`. Fresh cloud may then restore Cloud Live without presenting
old observations as current.

## 7. Local NMEA/AIS ingest

The default endpoint is UDP `127.0.0.1:10110`. AIS-catcher remains a separate
process, for example:

```text
AIS-catcher ... -u 127.0.0.1 10110
```

SeaWatch never controls RTL-SDR hardware. A maintained AIS decoder handles
`!AIVDM`/`!AIVDO` payloads; SeaWatch implements bounded framing, validation,
normalization, and lifecycle, not AIS bitfields. Valid single/multipart
position reports create observations. Invalid checksums, missing fragments,
unsupported messages, and malformed fields are ignored without escaping the
FastAPI lifecycle. Static messages may enrich existing internal state but
never create coordinates.

Valid tag-block timestamps become `observed_at`. If NMEA has no observation
time, local receive time is the only measured timestamp and is used explicitly;
`received_at` always records SeaWatch ingestion. Edge observations use
`source = "edge_ais"`, `synthesized = false`, and internal MMSI only. Invalid
frames do not refresh Edge freshness.

## 8. Replay versus real RF

Replay requires both an explicit enable setting and
`SEAWATCH_EDGE_REPLAY_FILE`. A path alone cannot enable replay, hardware absence
cannot enable it, and UDP/replay are mutually exclusive per consumer.

The cancellable reader sends fixture lines through the same decoder and edge
store as UDP with configurable interval/speed. Replay observations carry
`source=edge_replay`, `input_kind=replay`, and `replay=true`. They may be
measured recorded fixes (`synthesized=false`) but remain `EDGE_REPLAY` /
`本地接收重播`, never `EDGE_LIVE` / `本地 AIS 接收`.

## 9. Vessel identity and deduplication

MMSI is allowed only inside backend observation, store, and identity code. The
public API never contains MMSI, IMO, callsign, or an identifier derived by an
unkeyed/enumerable hash.

`VesselIdentityRegistry` uses a keyed HMAC for confidently known MMSI values,
with a backend-only `SEAWATCH_IDENTITY_KEY`, and a random process-local opaque
identifier when identity is uncertain. Reverse mappings resolve public track
requests without exposing source keys. Public values use an opaque `v_` token
with a collision-safe length and registry collision check. Production docs
require a stable secret for IDs that survive restarts; tests inject a fixed
non-production key. Without a configured key, the server generates a
process-local secret and warns once without revealing it.

Cloud and Edge merge only when both carry the same valid MMSI. Name,
destination, proximity, course, or timing are insufficient. Uncertain matches
stay separate. A reliable match presents the freshest observation appropriate
to the active mode; tracks are not spliced across stores in Phase 8.

## 10. Active view, caching, and provenance

`ActiveVesselView` reads immutable snapshots and may retain the prior active
snapshot for at most 300 seconds during transitions. Each feature adds:

```text
operating_mode: CLOUD_LIVE | EDGE_LIVE | EDGE_REPLAY | NO_LIVE_SOURCE | OFFLINE_DEMO
observation_origin: cloud | edge_rf | edge_replay | offline_demo
display_state: live | cached | stale
active_source: true | false
coverage: taiwan_wide_network_feed | local_rf | none | demo
observed_at: UTC timestamp
data_age_seconds: number
synthesized: boolean
```

On Cloud-to-Edge failover, a new RF fix is `edge_rf/live`. A retained cloud
fix remains `cloud/cached` or `cloud/stale` with `active_source=false`; it is
never counted as a local vessel. A reliable MMSI match lets the fresher active
observation replace the cached marker for the same public identity.

`NO_LIVE_SOURCE` returns bounded cached/stale data when available rather than
blanking the map. After expiry it returns an empty collection and never enters
Offline Demo automatically.

## 11. API compatibility

These routes and their existing core fields remain:

- `GET /live/health`
- `GET /live/vessels`
- `GET /live/vessels/{public_id}/track`

Existing consumers still find `status`, `provider`, `connected`,
`last_message_at`, `message_age_seconds`, `vessel_count`,
`reconnect_attempts`, and `last_error` in `/live/health`. Compatibility fields
describe the active view. Additive fields include `mode`, `coverage`,
`simulated`, and nested source summaries.

`/live/vessels` remains GeoJSON and retains existing properties while adding
Section 10 provenance. Attribution reflects actual returned sources rather
than being hard-coded. `/live/vessels/{public_id}/track` resolves the opaque ID
and reads only measured retained points from the owning active store; unknown
or expired IDs return `404`.

New `GET /resilience/status` example:

```json
{
  "mode": "EDGE_LIVE",
  "simulated": false,
  "coverage": "local_rf",
  "internet_available": false,
  "power_mode": "battery_ups",
  "cloud": {"fresh": false, "message_age_seconds": 84.0, "vessel_count": 1320},
  "edge": {
    "fresh": true,
    "input_kind": "udp",
    "message_age_seconds": 2.0,
    "vessel_count": 17
  }
}
```

`internet_available` means the cloud AIS feed is usable, not that a general
network probe succeeded.

New `GET /edge/health` reports receiver active/detected status, input kind,
bind host/port, last NMEA and valid AIS times, message age,
received/decoded/rejected counts, local vessel count, and a bounded last error.
It returns a normal inactive response when disabled or hardware is absent.

## 12. Frontend mode and transition experience

| Mode/copy | Traditional Chinese | English |
|---|---|---|
| Cloud | `雲端即時 AIS` | `CLOUD LIVE` |
| Cloud coverage | `臺灣廣域網路 AIS` | `Taiwan-wide network AIS` |
| Edge RF | `本地 AIS 接收` | `EDGE LIVE` |
| Edge coverage | `本地無線電 AIS` | `Local RF AIS` |
| Replay | `本地接收重播` | `EDGE REPLAY` |
| No source | `即時資料無法使用` | `LIVE DATA UNAVAILABLE` |
| Offline demo | `離線示範資料` | `OFFLINE DEMO` |

Edge RF and replay always state:

> 僅顯示本地天線可接收的船舶。  
> Shows only vessels receivable by the local antenna.

Replay additionally says the data is recorded and not live RF. Brief
non-blocking banners occur only on actual transitions:

- `雲端 AIS 無法使用，已切換至本地 AIS 接收器` / `Cloud AIS unavailable — switched to local AIS receiver`;
- `雲端 AIS 已恢復` / `Cloud AIS restored`;
- drill transitions are prefixed `模擬` / `SIMULATED`.

Cached/stale markers retain integrity badges and distinct styling. The map and
selection panel stay open. No old cloud point is called an Edge observation.

Power status is configured as `external` or `battery_ups` and displayed as
`外部電源` / `External Power` or `電池／UPS` / `Battery / UPS`, followed by:

> 韌性運作需要筆電電池或 UPS。  
> Power resilience requires laptop battery or UPS.

## 13. Offline map fallback

```text
NLSC online raster
      |
      | repeated tile/network failure OR active Edge/No-source mode
      v
local PMTiles (default /offline/taiwan.pmtiles)
      |
      | archive/protocol/style unavailable
      v
bundled emergency local style
  - simplified Taiwan coastline/outline
  - major commercial ports
  - local Taiwan/port labels
  - zero Internet requests
```

The frontend registers PMTiles before constructing MapLibre. The URL is
configurable; no archive is committed. Windows-compatible preparation/install
instructions place an operator-created archive outside Git.

Once NLSC is marked failed or the app clearly enters disconnected Edge
operation, the browser session stops selecting NLSC URLs. It does not retry on
every repaint. Explicit operator action or reload may start a new attempt.

The emergency outline is a small simplified extract of Natural Earth
public-domain geography with provenance recorded beside it and in
`docs/offline-map.md`. Existing commercial port points are bundled local
civilian context. No military detail is included.

## 14. Failure cases

| Failure | Required behavior |
|---|---|
| No RTL-SDR/AIS-catcher | Edge inactive/not detected; FastAPI and Cloud continue. |
| UDP bind failure | One bounded health/log error; no startup crash or hot loop. |
| Invalid frame | Ignore/increment rejection; do not refresh Edge freshness. |
| Missing multipart fragment | Expire bounded assembly; do not fabricate/crash. |
| Decoder unavailable | Edge inactive with actionable error; Cloud continues. |
| Replay missing/invalid | Replay inactive; never claim RF. |
| Cloud down, Edge fresh | Switch after stale threshold; retain labeled cache. |
| Both stale | `NO_LIVE_SOURCE`; bounded cached/stale data only. |
| Cloud briefly returns | Stay Edge until continuous recovery completes. |
| System clock changes | Monotonic elapsed decisions prevent flapping. |
| PMTiles absent | Emergency local map; never blank screen. |
| NLSC unavailable | Abandon for session; no endless retry. |
| Identity uncertain | Keep separate public vessels. |

Routine lack of NMEA is a health state, not an exception, and produces no
repeated noisy logs.

## 15. Security boundaries

- Edge defaults to loopback UDP `127.0.0.1:10110`; no public bind is a default.
- NMEA is untrusted: bound datagram/line length, multipart state, numeric ranges,
  and validate checksums.
- Cloud credentials remain backend-only; the browser never calls Open Waters.
- MMSI, IMO, callsign, identity keys, and internal source IDs never cross the
  public API boundary.
- Secrets are environment-only and never logged or committed.
- Replay and drill require explicit enable flags and retain simulated labels in
  API, UI, and logs.
- The drill has no remotely enabled production control endpoint.
- Offline assets contain public civilian context only.

## 16. Simulation-only failure drill

`scripts/resilience_drill.py` imports the real `ResilienceModeManager` with an
injected monotonic clock and controlled health snapshots; it does not duplicate
the state machine. An explicit `--enable-simulation` argument is mandatory and
every stage prints `SIMULATED`:

1. Cloud Live.
2. Simulated cloud outage.
3. Explicit Edge replay freshness.
4. `EDGE_REPLAY` active.
5. Simulated cloud restoration.
6. Recovery delay remains Edge Replay.
7. Cloud Live after the recovery duration.

The script may feed the recorded fixture through the real edge decoder/store.
It never alters a normal running server, disables networking, or claims RF.

## 17. Performance measurements

A fixed recorded fixture and `time.perf_counter_ns()` measure:

- accepted NMEA lines per second;
- completed-message decode latency;
- edge store update latency;
- `/live/vessels` latency at documented vessel counts;
- MapLibre GeoJSON update latency through the browser Performance API or a
  deterministic instrumented harness.

Reports record environment, sample count, warm-up, median, p95, and maximum.
Timing data exposes no vessel identity. No result is claimed before the command
is actually run on the demo machine.

## 18. Offline test matrix

All normal tests use recorded/minimal NMEA, injected clocks, mocked health,
local HTTP clients, and mocked MapLibre. They require no Internet, SDR,
AIS-catcher, PMTiles archive, or secret.

| Area | Required cases |
|---|---|
| NMEA | Position normalization, sentinels, time fallback/tag, attribution. |
| UDP | Multiple lines, multipart, oversized input, invalid frame ignored. |
| Edge health | Disabled, active/no data, valid data, invalid-only, bounded error. |
| Modes | Cloud healthy; cloud stale/Edge fresh; both stale. |
| Replay | Explicit replay → `EDGE_REPLAY`, never `EDGE_LIVE`; no auto-enable. |
| Hysteresis | Brief recovery stays Edge; stable recovery returns Cloud. |
| Offline Demo | Explicit only; no automatic failover. |
| Hardware absence | API/Cloud start and run without Edge hardware. |
| Identity | Same MMSI dedupes; uncertain identity does not; opaque test ID. |
| Privacy | No MMSI, IMO, callsign, secret, or raw Edge ID in API text. |
| Active view | Source selection, freshness, cache provenance/expiry. |
| Tracks | 30-minute Edge rolling track using decoded points only. |
| API | Existing `/live/*` schema compatibility and new health schemas. |
| UI | All modes, coverage explanation, power copy, transition banners. |
| Map | NLSC → PMTiles → emergency; no endless dead-source retry. |

Backend verification:

```powershell
python -m pytest -q -p no:cacheprovider --basetemp=C:\Projects\seawatch\.swtmp
```

Frontend verification:

```powershell
Set-Location apps/web
npm test
npm run build
```

## 19. Cloud-safe migration plan

1. Add health/mode types and tests without changing singleton wiring.
2. Wrap the global store/consumer as dedicated cloud state while `/live/*`
   still reads Cloud and current tests remain unchanged.
3. Add the identity registry and active-view facade in Cloud-only mode; verify
   compatibility/privacy before Edge.
4. Add pure edge decoding tests, then UDP/replay lifecycle disabled by default.
5. Add separate edge store and health routes; absent hardware stays normal.
6. Connect the real manager to the active view and test transitions with mocked
   health before frontend changes.
7. Extend `/live/*` additively; migrate frontend to mode/provenance fields.
8. Add PMTiles and emergency style without removing NLSC choices.
9. Add drill, measurement harness, and Windows runbooks.
10. Run full offline verification, an explicitly requested Cloud smoke check
    only when Internet is available, measurements, privacy scans, and
    `git diff --check`.

Open Waters parsing, subscription, reconnect behavior, and Taiwan bbox are not
rewritten unless a failing compatibility test proves a narrow change necessary.

## 20. Configuration contract

```text
SEAWATCH_LIVE_INGEST=false
SEAWATCH_EDGE_INGEST=false
SEAWATCH_EDGE_HOST=127.0.0.1
SEAWATCH_EDGE_PORT=10110
SEAWATCH_EDGE_REPLAY_ENABLED=false
SEAWATCH_EDGE_REPLAY_FILE=
SEAWATCH_EDGE_REPLAY_INTERVAL_SECONDS=1.0
SEAWATCH_CLOUD_STALE_SECONDS=30
SEAWATCH_EDGE_STALE_SECONDS=30
SEAWATCH_CLOUD_RECOVERY_SECONDS=20
SEAWATCH_IDENTITY_KEY=<backend-only secret>
SEAWATCH_POWER_MODE=external
SEAWATCH_OFFLINE_DEMO=false
SEAWATCH_RESILIENCE_DRILL_ENABLED=false
VITE_OFFLINE_PMTILES_URL=/offline/taiwan.pmtiles
```

Cloud and Edge can be enabled independently. Replay additionally needs its
enable flag. Drill and Offline Demo cannot be inferred from missing network or
hardware.

## 21. Documentation deliverables

- `docs/edge-ais-runbook.md`: Windows laptop, RTL-SDR, VHF/AIS antenna,
  AIS-catcher UDP, SeaWatch startup, health checks, and local-RF limitation.
- `docs/offline-map.md`: PMTiles preparation/install/licensing, emergency asset
  provenance, and no-large-archive Git policy.
- `docs/offline-startup-runbook.md`: battery/UPS, service sequence, disconnect,
  Edge verification, changing local positions, and offline map verification.
- `docs/phase8-edge-resilience-report.md`: tests, measurements, limitations,
  and mandatory Cloud/Edge/Demo/Power reality check.

## 22. Completion criteria

Phase 8 is complete only when:

1. Open Waters Cloud Live remains primary and regression tests pass.
2. Cloud/Edge stores, health, counters, freshness, and tracks are independent.
3. AIS-catcher UDP produces normalized observations and 30-minute Edge tracks.
4. Missing hardware never blocks API startup or Cloud Live.
5. Mode selection and monotonic recovery hysteresis are honest and stable.
6. Replay and Offline Demo remain explicit and never masquerade as live RF.
7. Public IDs are opaque/keyed; MMSI, IMO, and callsign never leave backend.
8. Cached/stale provenance survives failover without source relabeling.
9. `/live/*` stays compatible and new health endpoints expose source state.
10. UI distinguishes all modes with correct zh-Hant/English copy and always
    explains local-antenna coverage in Edge modes.
11. NLSC falls back to PMTiles then a zero-Internet emergency map without
    hammering dead online tiles.
12. Power status is External Power or Battery/UPS with no runtime claim.
13. The drill uses the real manager and cannot silently alter production.
14. Automated tests need no Internet, SDR, AIS-catcher, or PMTiles.
15. Performance is reported only from actual measurements.
16. Windows-first hardware/offline runbooks are complete.
17. No military tracking, logistics, deployment change, huge tile archive, or
    secret enters Phase 8.
