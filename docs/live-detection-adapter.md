# Live-to-detection adapter

## Purpose and boundary

The live-to-detection seam is provider-independent:

```text
provider -> LiveVesselObservation -> RollingTrackBuffer
         -> DetectionTrackAdapter -> detection.models.Track
         -> engine.analyze -> Event / Alert -> /detection/* -> Watch Floor
```

Provider-specific code ends when it produces `LiveVesselObservation`. The
adapter contains no Datalastic client, polling loop, browser behavior, or
provider credential handling.

## Engine contract

`engine.analyze(tracks, context, cfg=None, as_of=None,
density="message_level", feedback=None, watch=None)` consumes a list of whole,
time-ordered `Track` objects and one reusable `DetectionContext`. It recomputes
the supplied tracks on every call and returns the existing `AnalysisResult`
containing existing `Event` and `Alert` objects plus detector skip reasons.

The context is mutable: detector discard counters, allow-list state, learned
stop areas, vessel habits, traffic baseline, monitored bounds, and territory
may all live on it. Build or load it once for a surveillance area and reuse it.
Do not rebuild it for every observation. A caller that lacks the correct
historical/region context must supply an explicit empty or limited context and
surface that limitation; the adapter never substitutes the simulated region.

## Buffer and identity

`RollingTrackBuffer` retains normalized observations only. It sorts
out-of-order frames deterministically, removes repeated copies of the same
provider fix, rejects non-finite or out-of-range positions, and enforces
configurable limits for vessels, points per vessel, input batch size, retention
time, and stale-vessel age. A fix's content key includes its reported time,
position, movement/static fields, source, provider identity, and MMSI, but not
the server-local `received_at`: polling the same upstream fix again therefore
does not consume another trajectory slot. A changed reported time or position
remains a distinct observation. Same-time conflicting fixes remain buffered and
the track adapter selects one deterministically.

Time-based maintenance runs on both writes and reads. Retention-expired points
and stale vessels therefore disappear even while provider ingestion is idle,
and replaying an old fix cannot resurrect an expired vessel. Oversized iterables
are read only through the configured limit plus one and rejected before
mutation. Vessel-cap candidates are ranked once by newest reported timestamp
and stable identity, making selection permutation-independent and
`O(v log v)` for `v` candidate vessels. The clock is injectable for
deterministic tests.

A valid nine-digit integer MMSI groups the same vessel across sources. Missing,
invalid, or fractional MMSI values are never truncated or fabricated. Such
observations remain isolated under the backend-only `(source, provider_id)`
identity and stay in the buffer, but cannot become a Detection `Track` because
the teammate model requires a real MMSI. IMO, provider UUID, and vessel name
are never promoted to MMSI.

## Field mapping

| Live observation | Detection `Track` | Missing representation |
|---|---|---|
| valid `mmsi` | `mmsi` | observation is retained but not adapted |
| `observed_at` | `t` epoch seconds | required |
| `latitude`, `longitude` | `lat`, `lon` | invalid point rejected |
| `sog_knots` | `sog` | `NaN` |
| `cog_deg` | `cog` | `NaN` |
| `nav_status` | `status` | `None` when wholly absent; `-1` for a missing point in a partial array |
| `vessel_type` | `ship_type` via `history.ship_category` | `other` |
| `name` | `name` | MMSI internally |
| `destination` | `extra["destination"]` | omitted |
| `source` | `extra["sources"]` / `extra["point_sources"]` | required by live schema |
| `heading_deg` | `extra["heading_deg"]` | `None` per point |
| `synthesized` | `extra["synthesized"]` | `False` |

Detection has no native heading array, so heading is retained as backend-only
provenance and is not used by a detector. No positions or movement values are
interpolated or invented by the adapter. The existing engine-owned proximity
detector does resample between closely bracketed fixes on its analysis grid;
that behavior remains outside this seam.

## Eligibility and multi-vessel behavior

`engine.REQUIREMENTS` remains the authoritative capability matrix. The live
adapter exposes those results for its current tracks instead of duplicating
threshold logic. Actual live capabilities are:

| Detector family | Engine gate | Additional evidence/context |
|---|---|---|
| AIS gap | 6 points / 3 hours; all densities | one vessel; receiver/learned coverage and vessel habits affect whether a gap is meaningful |
| Loitering | 8 points / 30 minutes; message/hourly | one vessel; benign areas and habits suppress routine stops |
| Rendezvous / cluster | 8 points / 30 minutes; message/hourly | two or more vessels in the same call; status can suppress anchored/moored points |
| Zone entry | 2 points; all densities | configured sensitive-zone geometry is required |
| Position jump | matrix says 3 points; all densities | the current detector implementation itself requires 4 points; no historical context required |
| Identity conflict | 6 points / 10 minutes; message only | repeated implausible alternation on one MMSI |
| Status mismatch | 5 points / 15 minutes; message/sparse | nav-status array is required; meaningful speed/movement is needed to produce an event |
| Route deviation | 8 points / 1 hour; message/hourly | finite SOG plus a non-empty historical `TrafficBaseline` |
| Survey pattern | 24 points / 12 hours; message/hourly | geometric history on one vessel; used when no territory model is installed |
| Cable activity | 6 points / 45 minutes; message/sparse | territory/cable context and slow movement; nav status can alter the finding |
| Survey threat | 4 points; all densities | territory model; SOG and self-declared class/name/destination/status strengthen or enable individual rules |
| Dark rendezvous | fused from eligible gap plus loiter/rendezvous/cluster events | fleet-level temporal/spatial correlation; never produced from an isolated point |

The three-versus-four point position-jump mismatch is documented rather than
papered over in this adapter: eligibility can say the detector may run at three
points, but the detector safely produces nothing until it has four. Changing
that teammate engine contract belongs in the detection stack, not this seam.

Rendezvous and cluster detection require multiple vessels in one engine call.
Gathering context also compares loiterers, and dark-rendezvous fusion correlates
gaps with other vessels' loitering/rendezvous/cluster events. The analyzer
therefore sends all eligible buffered tracks together. A single observation or
short track reports `insufficient_data`/`not_applicable` and must not create a
trajectory-dependent alert.

## Analysis modes

`LiveDetectionAnalyzer(context, *, buffer=None, adapter=None,
density="message_level", config=None, feedback=None, watch=None)` requires a
caller-supplied context and retains it. Its public methods are `ingest`,
`tracks`, `eligibility`, `analyze`, and `update`; `analyze`/`update` return the
existing `AnalysisResult` type. An invalid density is rejected immediately.

One-shot Area Scan and a future continuous surveillance session use the same
callable seam:

```text
analyzer.update(observations) = ingest -> adapt all buffered tracks -> analyze
```

A one-shot scan normally has too little history for trajectory detectors. A
surveillance session calls the same method repeatedly; the bounded buffer
accumulates evidence until existing eligibility rules allow richer detectors.
When `as_of` is supplied, the analyzer filters buffered observations before
adaptation so future static metadata and point-aligned provenance cannot leak
into the earlier assessment. No polling or provider calls occur in this module.
Each provider refresh must be a finite batch no larger than the buffer's
`max_batch_observations` guard (100,000 by default).

## ML and path agent

The adapter calls `engine.analyze`, preserving deterministic detection and the
existing alert-fusion types. It does not train, load, or invent an ML result;
without a configured regional model, `Alert.ml` remains `None`. The existing
Detection service owns regional model loading and optional second-opinion
scoring. The path-analysis agent remains advisory and is not invoked for every
live observation. External language-model availability is never required for
core live detection.

## Privacy and integration hook

Raw MMSI and per-source identities remain backend-only. Any future API hook
must apply `engine.redact` with the SeaWatch identity registry before returning
payloads to the browser. `engine.redact` supplies raw MMSIs as strings, so the
callable must convert and handle the registry's optional result explicitly:

```python
def public_detection_id(raw_mmsi: str) -> str:
    public_id = registry.public_id_for_mmsi(int(raw_mmsi))
    if public_id is None:
        raise ValueError("detection payload contained an invalid MMSI")
    return public_id

public_payload = engine.redact(internal_payload, public_detection_id)
```

The future Datalastic/Area Scan branch only needs to pass its already-normalized
`list[LiveVesselObservation]` to a long-lived `LiveDetectionAnalyzer` associated
with the correct region context. No provider-specific field or client belongs
inside the adapter.

## Performance sanity

A local synthetic run on 2026-10-03 used eight five-minute observations per
vessel, spatially separated tracks, `message_level` density, an empty explicit
context, and Python `tracemalloc`. These are single-run engineering checks, not
service-level guarantees:

| Vessels | Retained points | Buffer update | Track conversion | `engine.analyze` | Peak traced memory |
|---:|---:|---:|---:|---:|---:|
| 100 | 800 | 0.192 s | 0.318 s | 0.769 s | 1.51 MiB |
| 500 | 4,000 | 0.838 s | 1.732 s | 3.914 s | 6.04 MiB |
| 1,000 | 8,000 | 1.618 s | 4.583 s | 8.116 s | 12.35 MiB |

All fixes were retained and adapted; the deliberately uneventful tracks
produced zero events and alerts. Batch ingestion takes one consistent clock
sample and applies linear time maintenance around the batch. The dominant cost
at 1,000 vessels was the existing whole-fleet detection invocation, as expected
for a whole-track rather than incremental engine.

After replacing repeated minimum searches with a single deterministic ranking,
a local five-run median capacity check (three runs for the 4,000-input row)
measured update-only time as follows. Each synthetic vessel contributed one
observation; object construction was outside the timed section:

| Vessel cap | Input vessels | Median update | Retained vessels |
|---:|---:|---:|---:|
| 100 | 100 | 0.003557 s | 100 |
| 100 | 200 | 0.006676 s | 100 |
| 500 | 500 | 0.015775 s | 500 |
| 500 | 1,000 | 0.039576 s | 500 |
| 1,000 | 1,000 | 0.031480 s | 1,000 |
| 1,000 | 2,000 | 0.094607 s | 1,000 |
| 1,000 | 4,000 | 0.171941 s | 1,000 |

## Known limitations

- MMSI-less observations cannot enter the current teammate `Track` model.
- Heading and synthesized/source provenance are retained but not detector inputs.
- Detection is whole-track recomputation, not an incremental algorithm.
- Context quality determines whether learned detectors are meaningful; an empty
  context is an explicit degraded mode, not a substitute for regional history.
- The adapter does not itself publish results through `/detection/*`; that later
  hook belongs where the live region is wired into the existing service/API.
