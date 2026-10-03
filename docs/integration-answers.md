# Detection system: answers to the integration handoff (section 23) and what was added for it

Entry point: `apps/api/seawatch/detection/engine.py` (`build_context`, `analyze`, `eligibility`, `redact`). Tests: `tests/unit/test_engine.py`.

```python
from apps.api.seawatch.detection import engine
ctx = engine.build_context(history_tracks, density="message_level")          # once, reuse
result = engine.analyze(tracks, ctx, density="sparse_live", as_of=now)       # -> events, alerts, skipped, stats
payload = engine.redact(alert.detail(), registry.public_id_for)              # before anything leaves the backend
```

## What was added because of the handoff

| item | status |
|---|---|
| One stable Python entry point (`analyze`) with the existing `Event` / `Alert` models as output | done |
| `not_applicable` / `insufficient_data` answers per detector and track (`result.skipped`) | done |
| `density` = `message_level` / `sparse_live` / `hourly_presence` selecting preset and allowed detectors | done |
| Whole-process lock around a context (contexts hold mutable counters) | done |
| `redact()` to replace raw MMSIs in payloads with the identity registry's public id | done; **must be applied by the integration at the API boundary** (see 19) |
| Path-analysis agent (advisory) with accept / reject and an export of decisions | done, see `docs/path-analysis.md` |
| Measured runtime and a per-detector requirement table | below |
| A `DetectionTrackAdapter` (live observations -> `Track`) | SeaWatch side; the contract is in answers 1-6 and 11-13 |
| Rolling-session detection (incremental) | not built; whole-track recompute is fast enough (answer 7, 15) |

## Answers

1. **`Track`** (`models.py`): `mmsi:str, name:str, ship_type:str, flag:str, t, lat, lon, sog, cog` (numpy arrays, equal length, `t` ascending epoch
   seconds), optional `status` (int array, AIS nav-status codes, 0 engine, 1 anchor, 3 restricted manoeuvre, 5 moored, 8 sailing, -1 unknown),
   `imo:str`, `extra:dict` with `destination`, `subtype` (registry class, e.g. "Research"), `tow_t` (timestamps when the destination announced
   towing). `ship_type` is one of cargo, tanker, fishing, passenger, ferry, tug, pilot, sar, service, dredger, pleasure, other (`history.ship_category`).
2. **Mandatory:** `mmsi, t, lat, lon`. Everything else may be NaN / None; speed is then derived from position steps (`mentor.to_tracks`).
3. **Detectors that work on lat/lon/time only:** `ais_gap`, `loitering` (stay-points), `rendezvous`, `cluster`, `zone_entry`, `position_jump`,
   `survey_pattern`, and the territory / pattern part of `survey_threat`.
4. **Need more:** `status_mismatch` and the nav-status factor need `status`; the destination / towing factor and registry factor need `extra`;
   `route_deviation` and the velocity factor want `sog`; `identity_conflict` needs message-level cadence. `engine.REQUIREMENTS` is the machine-readable table.
5. **Minimums** (`engine.REQUIREMENTS`): gap 6 points over 3 h; loiter / rendezvous / cluster 8 points over 30 min; jump 3 points; zone entry 2 points;
   route deviation 8 points over 1 h; survey pattern 24 points over 12 h; survey threat 4 points (declaration rules need no history, pattern
   rules need the survey-pattern minimum). The path agent needs windows of 6 h with at least 6 points and no gap above 6 h.
6. **Uniform sampling is not required.** Detectors interpolate or bracket across gaps up to `bracket_s`; gaps are themselves evidence.
7. **Incremental:** not incremental. `analyze` recomputes the tracks it is given (whole track). Cheap enough to call per scan (see 15); to analyse
   one updated vessel pass just that track plus the shared context. Group detectors (rendezvous, cluster) need the neighbours in the same call.
8. **Cache across scans:** the `DetectionContext` (baseline, learned stop areas, vessel habits, territory). Rebuild when history is refreshed.
9. **New live region:** `engine.build_context(history_tracks, density)`; it fits `TrafficBaseline`, `LearnedContext`, `VesselHabits` from the
   earlier tracks of the same area (about 11 s for 6,000 vessels / one day). With no history, pass an empty context: gap / loiter / rendezvous
   fall back to absolute thresholds and are noisier; the survey-threat declaration rules still work.
10. **GFW as seed:** its hourly cells can seed the traffic baseline and stop areas (ports, anchorages) of a live region, but not vessel habits at
    minute resolution. Use `density="hourly_presence"` contexts for GFW, a separate `message_level` context for live data, and keep both.
11. **Cadence:** the dense preset was tuned on ~6 minute median reporting. Acceptable for loitering / rendezvous: a report at least every 10 minutes.
12. **Too sparse:** `analyze` marks the track `insufficient_data` for the detectors that cannot work and runs the rest (zone entry, jump,
    declaration-based survey rules). A one-shot scan produces zone entries and declarations only, never loitering or patterns.
13. **Duplicates / out of order:** the adapter must sort by `t` and drop exact duplicate `(mmsi, t)` before building tracks (detectors assume
    ascending time). `mentor.normalise` does `drop_duplicates(["mmsi","t"])` and a stable sort; reuse it.
14. **Concurrency:** not safe on one context from several threads without the lock; `engine.analyze` holds `engine._LOCK`. Use one context per
    surveillance area. The Watch Floor service (`DetectionService`) has its own lock.
15. **Runtime** (this machine, message-level, dense preset, 6,000-vessel context): 100 vessels 0.4 s; 500 vessels 1.9 s; 2,000 vessels 12.4 s
    (118k reports). Context build 11 s. Rendering path reviews adds about 0.1 s per image; a Claude call per window adds the model latency.
16. **ML models:** loaded once per region by `ml.load(path, features)` (joblib). The Watch Floor service scores windows in a background thread.
17. **No trained model:** alerts are produced without the `ml` block (`ml_agreement` is null); nothing else changes. Live Taiwan has none today.
18. **Internal identifiers:** `mmsi` (all detectors, identity hygiene, watch-list matching on MMSI / IMO), `imo` (watch-list), `name` (declaration
    rules, fishing-name heuristics). Provider UUIDs are not used.
19. **Stable for the frontend:** the `/detection/*` payloads in README section 6. Known gap: they currently carry **raw MMSIs** (`mmsi`, `mmsis`,
    `vessels[].mmsi`, track keys, path-review ids). Apply `engine.redact(payload, registry.public_id_for)` at the integration boundary (and make
    the public id the key the frontend uses for track lookup).
20. **Hide or caveat in a live demo:** the learned path-shape model, survey-shape classifier and region-transfer model (not validated); hourly-region
    recalls (weak); `taiwan-day`-style dense noise until the live context has several days of history; route deviation and dark rendezvous on short
    histories; the modelled 12 / 24 nm / EEZ lines as legal boundaries; the path agent as anything but advisory.

## Open items the SeaWatch side must supply or decide

- The adapter: provider observation -> `Track` per vessel, keyed by validated MMSI, bounded retention, `observed_at` as `t`, and `data_density`.
- Which density label a live session gets (`sparse_live` for one-shot scans, `message_level` once a vessel has a report every <= 10 minutes).
- Registry `subtype` and `destination` from the provider if available (they power the research gate and the towing factor).
- A decision whether live GFW baseline context is shown beside the detection alert (separate service, join on validated MMSI).
- Authentication for the agent endpoints when a paid model is used (`SEAWATCH_PATH_AGENT=claude`, `ANTHROPIC_API_KEY`, backend only).
