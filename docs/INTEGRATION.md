# Integrating the detection system: step by step

Branch: `feat/detection-stack`. Read the README section "Detection stack and hand-off guide" first, then `docs/integration-answers.md` (answers to the
handoff questions) and `docs/rules-walkthrough.md` / `docs/threat-definition.md` (what the rules mean).

## 1. What is on the branch

| area | where |
|---|---|
| detection engine, rules, threat model, ML, path agent | `apps/api/seawatch/detection/` (`engine.py` is the stable entry point) |
| HTTP routes | `apps/api/seawatch/api/detection.py` (`/detection/*`), already registered in `main.py` |
| Watch Floor UI | `apps/web/src/features/watch/` (used by the WATCH FLOOR tab in `App.tsx`) |
| map layers (cables, limits), labels, small geo data | `data/geo/*.geojson`, `data/labels/` |
| scripts (data builders, training, measurements) | `scripts/` |
| tests | `tests/unit/test_detection_stack.py`, `test_path_agent.py`, `test_engine.py`, `test_alert_policy.py` |

## 2. What is NOT on the branch (git-ignored) and how to get it

| item | why | how |
|---|---|---|
| `data/processed/*.pkl`, `*.parquet` (regions) | large / licensed data | `python scripts/build_taiwan_ais.py DAY.csv RESEARCH_01.csv RESEARCH_02.csv` for the April 2026 regions; SF Bay: `scripts/setup_sfbay_data.py`; GFW hourly: `SEAWATCH_DATA_ROOT` |
| `data/models/*.joblib` | trained per region | `scripts/train_region_ml.py` (SF), `scripts/train_tw_ml.py` (Taiwan hourly). None is needed for live Taiwan; alerts then have no ML block |
| `data/geo/ne_10m_*.geojson`, `cable-geo.json` | raw downloads | only to rebuild `taiwan_land/neighbour_land/taiwan_cables/zone_lines` (`build_taiwan_geo.py`, `build_cables.py`, `build_zone_lines.py`); the compact outputs are committed |
| `.env` / API keys | secrets | never commit; see section 4 |

With no data files the app starts in the fully simulated `taiwan` region, which is enough to test the UI and the integration.

## 3. Run and verify

```bash
python -m uvicorn apps.api.seawatch.main:app --port 8000     # from the repository root
cd apps/web && npm install && npm run dev                     # http://localhost:5173
python -m pytest tests/unit/test_detection_stack.py tests/unit/test_path_agent.py tests/unit/test_engine.py tests/unit/test_alert_policy.py -q
```

Two tests in `tests/unit/test_web_serving.py` fail on the installed FastAPI (route objects have no `.path`); they failed before this branch too.

## 4. Environment variables

| variable | meaning |
|---|---|
| `SEAWATCH_REGION` | start-up region: `taiwan`, `sf-bay`, `taiwan-gfw`, `taiwan-day`, `taiwan-research` |
| `SEAWATCH_DATA_ROOT` | drive with the GFW hourly files (default `D:\SeaWatch`) |
| `SEAWATCH_PATH_AGENT` | `offline` (default, rules only), `featherless` (rules + language-model second reading), `claude` |
| `FEATHERLESS_API` | Featherless key (`NAME=value` or `NAME: value` in the process environment or a `.env` file; `SEAWATCH_ENV_FILE` can point at the file) |
| `SEAWATCH_FEATHERLESS_MODEL` | default `Qwen/Qwen2.5-7B-Instruct` (tested; Llama-3.2-3B is gated and weak, Qwen-14B no better) |
| `ANTHROPIC_API_KEY`, `SEAWATCH_AGENT_MODEL` | for the Claude reviewer (not exercised against the live API in this repo) |

All keys are backend-only. The frontend never sees them.

## 5. Wiring live data (the integration work)

1. **Adapter (SeaWatch side).** Turn each vessel's validated live observations into a `Track` (`models.py`): `mmsi, name, ship_type, flag, t, lat, lon, sog,
   cog` (numpy arrays, ascending `t`), optional `status` (AIS nav-status codes), `imo`, `extra={"destination": ..., "subtype": ...}`. Sort by time and drop
   duplicate `(mmsi, t)`. `ship_type` values: `history.ship_category`. Use `observed_at` as `t`, never the scan time.
2. **Context.** Build once and reuse: `ctx = engine.build_context(history_tracks, density="message_level")`. With no history pass an empty list; the survey-threat
   declaration rules still work, gap / loiter / rendezvous become noisier (and are switched off in the Taiwan regions anyway).
3. **Analyse per scan.** `result = engine.analyze(tracks, ctx, density="sparse_live" | "message_level", as_of=now)`.
   `result.skipped` lists detectors that could not run (`not_applicable` / `insufficient_data`): show that, do not hide it. One analysis per context at a time
   (the engine holds a lock).
4. **Serve it.** Either expose `result.alerts` through the existing `/detection/*` shapes (`alert.summary()` / `alert.detail()`), or register a live region in
   `service.py` `REGIONS` + `DetectionService` (see how `taiwan-research` is built in `mentorworld.py`). The Watch Floor reads only the `/detection/*` contract.
5. **Privacy boundary.** The payloads carry raw MMSIs. Wrap every outgoing payload: `engine.redact(payload, registry.public_id_for)` so the browser only sees
   public ids, and use the public id as the key for track lookup. Raw MMSI / IMO / provider UUIDs must stay on the backend.
6. **Paid-endpoint safety.** The path-review image and decision routes are unauthenticated like the rest of `/detection/*`; put the same auth in front as the
   Area Scan endpoint before any public deployment, especially when `SEAWATCH_PATH_AGENT` is not `offline`.

## 6. Behaviour decisions already taken (do not undo without the team)

- Levels (HIGH / MEDIUM / LOW) are a sort order. The system reports whatever COULD be a threat; survey-threat findings (including domestic R0) are never
  dropped by the minimum-risk cut. Towing in the EEZ by a foreign vessel is HIGH; Taiwan-registered is reported as R0 (low).
- Fishing-type vessels are not discounted: routine behaviours are merged into one area summary per 0.25 degree cell and day. Judge by place and behaviour.
- In the Taiwan regions only these run: survey threat / pattern, protected-zone entry, position jump, identity conflict, cable activity. Gaps, loitering,
  rendezvous, clusters and route deviation remain in `sf-bay` and the simulated region until they can be measured.
- Velocity factor: 2-6 kn for message-level data (measured on real survey runs), 5-10 kn for hourly.
- The learned path-shape model and the survey-shape classifier are experimental and must not feed alert scores. The path agent is advisory.
- The 12 nm / 24 nm / EEZ lines and the cable routes are modelled / approximate public data, not legal baselines or survey-grade positions. Keep the provenance
  label in the UI (`/detection/layers` returns an attribution string).

## 7. Acceptance checks before demo

- Open the app, choose `taiwan-research`: expect 22 survey-threat alerts, TAN SUO ER HAO (towing in the EEZ) HIGH, factor cards T/V/A/P/D/N/C on the alert,
  a "Path review (advisory)" section with a picture and agree / disagree buttons.
- `GET /detection/assessment` returns the funnel and discard counts; `GET /detection/rulebook` returns the live thresholds.
- A track with fewer points than a detector needs produces `insufficient_data`, never an alert.
- No raw MMSI appears in any browser-visible payload after `redact()`.
