# Datalastic Area Scan — design specification

Date: 2026-10-03 (Asia/Taipei)
Status: **Approved for implementation.**

## Purpose

Add a real, explicit, human-triggered maritime area-scan workflow to SeaWatch
using Datalastic Live AIS, while preserving the existing Open Waters continuous
feed as an optional fallback. A reviewer draws a rectangle or polygon, presses
**Scan Area**, receives only real provider observations covered by that geometry,
and can open the existing Vessel Panel and Vessel Intelligence workflow.

This is a situational-awareness and human-review feature. It does not classify
threats, infer criminal intent, fabricate observations, or substitute demo data
when the real provider is unavailable.

## Current architecture and protected boundaries

- `OpenWatersProvider` implements a WebSocket-specific `LiveAisProvider` and is
  consumed by the long-running `AisIngestConsumer`. That contract remains intact.
- `LiveRuntime` owns the process-wide cloud/edge stores, identity registry,
  resilience manager, and active view.
- `/live/vessels`, `/live/health`, and `/live/vessels/{id}/track` expose the
  existing privacy-safe live contract.
- `VesselIdentityRegistry` is the sole public-identity implementation. Valid
  MMSIs are HMACed with the supplied stable `SEAWATCH_IDENTITY_KEY`.
- The GFW historical store uses that same process-wide registry. GFW remains the
  only historical baseline and represents standardized vessel-presence data,
  not raw AIS messages.
- The frontend uses React, TypeScript, and MapLibre. It calls only the SeaWatch
  API through the shared `getBaseUrl()` policy.
- `VesselPanel` and `VesselIntelligenceCard` consume the existing
  `LiveVesselFeature` and opaque public ID. Their historical, route, geographic,
  satellite, Unknown/unavailable, and human-review semantics remain unchanged.
- `httpx`, Shapely, and PyProj are already pinned dependencies. No new mapping or
  geospatial framework is needed.

## Provider architecture and startup selection

Datalastic is not inserted into `LiveAisProvider` or `AisIngestConsumer`.
Instead, add a request-driven `DatalasticClient` plus
`DatalasticAreaScanProvider`/`AreaScanService`, owned by `LiveRuntime`.

Provider selection rules are exact:

1. An explicitly configured `SEAWATCH_LIVE_INGEST` value is preserved exactly.
2. If that variable is absent and `DATALASTIC_API_KEY` is configured,
   `start_demo.ps1` defaults the old Open Waters ingest to disabled.
3. If both are absent, preserve the existing anonymous Open Waters demo default.
4. Datalastic is always the primary provider for `POST /live/area-scan` when its
   key is configured. Area Scan never silently falls back to Open Waters or demo
   data.
5. A Datalastic outage never prevents SeaWatch startup.

The key is read only by backend configuration. The configurable base URL is an
internal/test seam and defaults to `https://api.datalastic.com/api/v0/`.

## Datalastic client contract

The async client sends `x-api-key` as a header only and supports:

- `GET /stat` for cached provider status;
- `GET /vessel_inradius` for explicit circle queries.

`GET /vessel` enrichment is deferred until the complete Area Scan workflow and
all verification gates pass. It is not part of this implementation.

Use typed internal models for status, provider vessels, circle queries, and
errors. Configure short connect/read timeouts. Provider failures map to fixed
categories: `not_configured`, `timeout`, `connection`, `authentication`,
`rate_limited`, `upstream`, `malformed_response`, and
`unsuccessful_response`. Raw response bodies, request URLs, exception strings,
`user_id`, and secret values are never logged or serialized.

### Shared rate-limit budget

One area scan owns one retry budget shared across all of its circles:

- at most two provider requests execute concurrently;
- the whole scan may perform at most one retry after a `429`;
- a short numeric `Retry-After` may be awaited, capped at five seconds;
- a missing, invalid, HTTP-date, or longer value is not slept through in the
  interactive request; return a sanitized temporary-unavailable result and, when
  safe, a bounded `retry_after_seconds` value;
- no circle receives an independent retry allowance.

## Cached provider health

When Datalastic is configured, startup schedules one non-blocking `/stat` probe.
The task is isolated from startup success and updates an in-memory status object.
`/live/health` reads that cached object and never starts provider traffic.
Global `/health` also never starts Datalastic traffic.

The safe public status is additive and contains only:

- `provider: "datalastic"`;
- `configured`;
- `reachable` (`true`, `false`, or `null` before the first probe completes);
- `key_status` (`valid`, `invalid`, or `unknown`);
- `addons` (`true`, `false`, or `null`);
- safe request/rate-limit remaining values when available;
- `last_success_at`;
- `last_error_category`.

The existing Open Waters health shape remains compatible when Datalastic is not
configured. Datalastic errors appear only as the fixed category, never raw text.

## Area Scan API

Add `POST /live/area-scan` and permit `POST` in the existing CORS configuration.
CORS is not authentication. The paid endpoint requires either a valid
short-lived signed bearer capability or the corresponding `SameSite=Strict`,
`HttpOnly` capability cookie. `POST /live/area-scan/session` exchanges a
constant-time-verified controlled-demo operator credential for that cookie.
Both flows fail closed when the server-only signing configuration is invalid.
The signing and operator values are independent server-side secrets of at
least 32 bytes. The session request is capped at 8 KiB, never reflects the
credential, and returns only `{authenticated, expires_in_seconds}` with
`Cache-Control: no-store`. Its 15-minute HMAC-SHA256 capability is scoped to
Area Scan and placed in a `Secure` cookie by default. Loopback HTTP use requires
the explicit `SEAWATCH_AREA_SCAN_ALLOW_INSECURE_COOKIE=true` transport
exception, and the server honors it only for loopback request hosts; there is
no authentication bypass. Frontend JavaScript receives
neither the signed capability nor any permanent secret.

Cookie-authenticated scans require `application/json` and the non-simple
`X-SeaWatch-Area-Scan: 1` confirmation header. This prevents a same-site
sibling origin from using a simple cross-origin request to spend provider
credits; the signed capability remains the authentication mechanism.

Capability verification occurs before the scan body is read. One process-wide
admission controller then atomically reserves the accepted scan and its maximum
provider-request cost (all covering circles plus the single shared retry).
Defaults are four scans and 32 reserved provider calls per 60 seconds. Together
with the hard 64-KiB scan-body ceiling, 512-coordinate geometry cap, 16-circle
cap, and global provider concurrency of two (including `/stat`), admission
rejection starts zero provider calls. Invalid limit configuration disables Area
Scan while leaving the rest of the API available.

The request is:

```json
{
  "geometry": {
    "type": "Polygon",
    "coordinates": [[[120.0, 22.0], [120.5, 22.0], [120.5, 22.5], [120.0, 22.5], [120.0, 22.0]]]
  }
}
```

Coordinate order is always `[longitude, latitude]`. Polygon holes are accepted
and respected. `MultiPolygon`, unclosed/invalid/self-intersecting polygons,
non-finite or out-of-range coordinates, excessive coordinate counts, zero-area
geometry, and antimeridian-crossing geometry are rejected before provider calls.

The response is independent of the ordinary polled-vessel collection:

```json
{
  "source": "datalastic",
  "scanned_at": "2026-10-03T09:00:00Z",
  "cached": false,
  "scan": {"geometry_type": "Polygon", "provider_queries": 4},
  "total": 37,
  "vessels": ["existing LiveVesselFeature objects"]
}
```

The route reads no more than 64 KiB. Invalid input returns `422`, oversized input
returns `413`, and authentication failure returns `401` or `403`, all before
provider traffic. An unconfigured or unavailable provider returns a sanitized
`503`; local admission returns `429`. Upstream `Retry-After` is exposed only
when it is a bounded integer from 0 through 5 seconds. No provider response is
replaced by illustrative vessels.

## Deterministic polygon covering

Use Shapely and PyProj with a local azimuthal-equidistant metric projection
centered on the validated polygon.

1. Normalize longitude/latitude geometry and project it to meters.
2. For a small polygon, use one circle centered on the projected bounds center
   with the smallest sampled WGS84 boundary radius rounded up after an absolute
   and relative numerical/geodesic safety margin. Never default it to 45 NM.
3. Otherwise, overlay a deterministic square grid anchored to the projected
   coordinate origin. The cell diagonal fits inside a 45-NM circle. Select cells
   whose closed cell polygon intersects the selected polygon, and use each cell
   center as a query center.
4. Compute every required circle before any provider call. Every query radius is
   at most 45 NM, with an absolute validation guard of 50 NM.
5. If more than 16 circles are required, reject with:
   `Selected area is too large. Draw a smaller region.`
6. Query all accepted circles, group Datalastic UUID evidence first, and admit a
   valid MMSI only when the UUID/MMSI evidence is unambiguous. Missing MMSI can
   inherit one consistent UUID group's MMSI; placeholder or conflicting values
   poison historical joining. Conflicting UUIDs sharing an MMSI remain separate
   provider-local vessels. UUID/IMO may support within-provider deduplication
   only and never become historical identity.
7. Apply the final WGS84 filter using Shapely `polygon.covers(point)`, so boundary
   vessels remain included and vessels in polygon holes remain excluded.
8. Sort normalized observations deterministically before public serialization.

The cover is conservative and deterministic, not mathematically minimal.

## Identity, privacy, and track observations

A valid nine-digit Datalastic MMSI is passed to the existing process-wide
`VesselIdentityRegistry`, producing the same HMAC public ID as a matching GFW
historical vessel under the same stable `SEAWATCH_IDENTITY_KEY`.

IMO and Datalastic UUID are never cross-source historical identities. A vessel
without valid MMSI receives a provider-scoped, process-local opaque public ID
through the existing registry and can never produce a fabricated GFW match.

Only normalized `LiveVesselObservation` values enter the bounded in-memory scan
track store. Repeated real scans may extend a real track. The public response,
track response, errors, logs, and cache never expose MMSI, IMO, Datalastic UUID,
API key, or `/stat` `user_id`.

Area Scan state remains separate from the ordinary Cloud/Edge live store and
resilience selection. `GET /live/vessels/{id}/track?source=datalastic` resolves
only the bounded Area Scan track store. The unqualified endpoint preserves the
ordinary active-view-first behavior.

## Cache

Use a bounded process-local 45-second TTL cache. Canonicalize valid geometry
before hashing with exact normalized WKB plus the provider/cover algorithm
version; do not round coordinates. Equivalent ring ordering should hit the same
key, while distinct sub-microdegree geometry must not share a result.

Cache only privacy-safe normalized scan results and safe response metadata.
Identical concurrent requests coalesce. A cache response exposes only
`cached: true`; no internal key, raw provider identifier, or secret metadata is
public. Nothing is persisted.

## Frontend interaction

Implement MapLibre-native drawing with no Kepler.gl or new map engine:

1. Click **Area Scan**.
2. Authenticate with the out-of-band controlled-demo operator credential. The
   browser receives only an HttpOnly short-lived capability cookie.
3. Select **Polygon** or **Rectangle**.
4. Draw without any provider request.
5. Keep the completed geometry visibly outlined and lightly filled.
6. Show a compact panel with selection summary, **Scan Area**, and **Clear**.
7. Call SeaWatch `POST /live/area-scan` with credentials included only on
   **Scan Area**.
8. Show loading, provider-unavailable, result count, scan time, query count, and
   cached state honestly.
9. Render results as a persistent, visually emphasized Area Scan layer while
   retaining the ordinary live layer separately.
10. Clicking a scan vessel opens the existing `VesselPanel` and
   `VesselIntelligenceCard` using its opaque ID.
11. Clear removes geometry/results and returns to the ordinary map state.

Pan, zoom, mouse move, drawing, completing a shape, and ordinary eight-second
live refreshes never invoke Datalastic and never overwrite active scan results.
The frontend immediately clears the operator credential after submission and
contains neither that credential, the signed capability, provider/signing keys,
nor a Datalastic base URL. Scan generations and abort controllers prevent older
or cleared requests from publishing over the latest overlay. A `401` or `403`
returns the panel to explicit operator authentication.

## Startup and runbook

`start_demo.ps1` reports exactly whether the Datalastic key is configured without
printing it. It never creates `SEAWATCH_IDENTITY_KEY`; operators must supply the
same stable private key used by live and historical identity.

Before invoking npm/Vite, the script temporarily removes all `SEAWATCH_*` and
`DATALASTIC_*` values plus `GFW_API_TOKEN` from the child environment, then
restores them for FastAPI. Permanent backend secrets therefore do not cross the
frontend toolchain boundary.

The demo-readiness runbook documents the server-side environment, Secure-cookie
default and explicit loopback exception, startup, browser URL, explicit
`?demo=vessel` illustrative scenario, Area Scan workflow, and the separation
between Datalastic Live AIS and the SSD-backed Global Fishing Watch historical
vessel-presence baseline.

## Verification

All automated provider tests use mocked HTTP and consume no credits. Required
coverage includes authentication, secret non-disclosure, client failure modes,
shared retry behavior, geometry validation/covering, boundary/hole filtering,
deduplication, cache/coalescing, identity joining, health sanitization, startup
selection, Open Waters fallback, draw modes, explicit-submit behavior, result
overlay persistence, selection integration, and frontend source isolation.

After focused suites pass, run the full backend suite, full frontend suite, and
production build (`tsc --noEmit` plus Vite). Only then, if the environment has a
key, perform exactly one `/stat` call and one small 1-NM Taiwan
`/vessel_inradius` call, reporting only safe status/count/cost/rate-limit fields.

Do not commit, push, merge, stage, or commit generated output during this
review. Report the complete unstaged diff for the primary implementer.
