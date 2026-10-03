# SeaWatch

**Explainable Maritime Intelligence & Resilience Decision Support**

*TDTH 2026 — Maritime Track Anomaly & Grey-Zone Behavior Alerting*

---

## Overview

SeaWatch is an **AI-assisted geospatial decision-support system** that analyzes
maritime vessel trajectories and surfaces behavior patterns that warrant human
review.

By combining AIS data processing, trajectory analytics, and explainable ranking
methods, SeaWatch helps analysts answer:

- What changed in this trajectory?
- Why is this behavior different from the baseline?
- Which behaviors require further investigation?

SeaWatch is a **human-in-the-loop decision-support platform** — not an autonomous
system, threat classifier, or automatic judgement engine.

---

## Problem

Modern maritime environments generate large-scale vessel movement data. Within
this data, a wide range of vessel behavior patterns coexist, and most of them are
routine.

The challenge is not only detecting unusual patterns, but also:

- identifying behaviors that genuinely differ from the norm
- explaining *why* a behavior stands out
- reducing false alerts and analyst fatigue
- supporting human decision-making rather than replacing it

SeaWatch focuses on **explainable behavioral intelligence rather than black-box
prediction**.

---

## System Architecture

```text
AIS Historical Data
        ↓
Trajectory Processing
        ↓
Movement Feature Engineering
        ↓
Explainable Anomaly Ranking
        ↓
Human Investigation Dashboard
        ↓
Emergency Logistics Simulation
```

---

## Core Capabilities

### Maritime Trajectory Intelligence

- AIS historical data ingestion
- Vessel trajectory preprocessing
- Temporal and geospatial analysis
- Movement behavior modeling

### Explainable Anomaly Ranking

- Behavior deviation scoring
- Feature-based explanations
- Transparent ranking logic
- Human-in-the-loop review workflow

### Resilience Decision Support

- Maritime situation awareness
- Disruption scenario simulation
- Emergency logistics extension

---

## Technology Stack

### Data & Geospatial Processing

- Python
- Pandas
- PyArrow
- PyProj
- Shapely

### Machine Learning

- Scikit-learn
- Statistical anomaly ranking methods
- Explainable feature-based analysis

### Application Layer

- FastAPI (`/detection/*`, `/resilience/*`)
- React + TypeScript
- MapLibre

### Optimization

- NetworkX

---

## Data

The current prototype is built on:

- NOAA MarineCadastre AIS GeoParquet
- Historical AIS observations
- WGS84 geospatial processing

SeaWatch treats **AIS data as behavioral observations**. The system does not
claim intent classification and does not automatically determine the purpose or
identity of a vessel.

---

## Detection stack and hand-off guide (for UI integration)

This section describes everything built on top of the original data foundation: the behaviour detectors, the Taiwan
survey-threat model, the ML models, the data regions, the API the UI talks to, and what is planned next. Alerts are
**candidates for human review**. Nothing here asserts intent or illegality, and every alert carries its evidence, innocent
explanations and what AIS cannot tell you.

### 1. How it fits together

```text
AIS (real / simulated)  ->  tracks (Track objects)  ->  context learned from history (ports, normal traffic, vessel habits)
        ->  deterministic detectors  ->  events (kind, severity, confidence, evidence, metrics)
        ->  fusion: noisy-OR risk, grouping, floors, discounts, operator feedback  ->  alerts (HIGH / MEDIUM / LOW)
        ->  optional ML second opinion per alert  ->  /detection/* API  ->  Watch Floor UI
```

Code: `apps/api/seawatch/detection/` (Python), API: `apps/api/seawatch/api/detection.py`, UI: `apps/web/src/features/watch/`.
Longer write-ups: `docs/detection-stack.md`, `docs/rulebook.md` (generated from the live thresholds), `docs/taiwan-real-data.md`,
`docs/research-vessel-data.md`, `docs/path-analysis.md`, `docs/integration-answers.md`, `docs/rules-walkthrough.md`, `docs/threat-definition.md`, `docs/real-outcomes.md`.

### 2. Run it

```powershell
.\scripts\run_demo.ps1                       # API on :8000 and web on :5173
# or by hand:
python -m uvicorn apps.api.seawatch.main:app --port 8000
cd apps/web; npm run dev
python -m pytest tests/unit/test_detection_stack.py -q      # 12 detection tests
```

`SEAWATCH_REGION=<id>` chooses the start-up region (the header drop-down switches live). Default order: `taiwan-research`,
`taiwan-gfw`, `sf-bay`, then `taiwan` (simulated) if no data is present. Data caches live in `data/processed/` (git-ignored); build
them with the scripts in section 7. Use `uvicorn` from the repository root, not from `apps/api`.

### 3. Regions (data sets the API can serve)

| id | data | injected events | notes |
|---|---|---|---|
| `taiwan` | fully simulated | yes, labelled, incl. 2 research-vessel cases + 1 benign look-alike | works with no data files |
| `sf-bay` | real NOAA AIS, 3 Jan 2024 | yes | where the detectors were first measured |
| `taiwan-gfw` | real hourly vessel presence (Global Fishing Watch, Sept 2026, ~11 km cells) | yes | hourly preset; no speed/status/destination |
| `taiwan-day` | real message-level AIS, one full day (3 Apr 2026) with research vessels merged | no | national-threat focus: only survey threats / patterns, zone entries, spoofing and identity conflicts (about 23 alerts) |
| `taiwan-research` | real message-level AIS of ~80 research-type vessels, 1-16 Apr 2026 | no | only survey rules are shown (the fleet sits outside the learned coverage) |

Gaps, loitering, rendezvous, clusters and route deviation are switched off in the Taiwan regions (insufficient data and noise; see `docs/rules-walkthrough.md` section 8) and stay active in `sf-bay` and the simulated `taiwan` region.

Real regions have no labels, so `/evaluation` returns `unlabelled: true` there. The UI badge reads `SIMULATED DATA`,
`REAL AIS + INJECTED EVENTS` or `REAL AIS` from `scenario.data_kind` (`simulated | real_plus_injected | real`).

### 4. Deterministic algorithms

All thresholds live in `config.py` (`DetectionConfig`) with three presets: default (minute-level, sparse coast), `hourly()`
(11 km cells) and `dense()` (minute-level, busy fishing waters). Every threshold is exposed to the UI through `/config`.

**Context learned from history (no hand-drawn zones):** `TrafficBaseline` (how much traffic each cell normally sees),
`LearnedContext` (habitual stopping areas such as ports and anchorages, reporting coverage), `VesselHabits` (where each vessel
routinely dwells, its own normal silence length, peers of the same type), per-zone routine visitors. This is why the same code runs
on a new coast.

**Behaviour detectors (`detectors.py`):**

| kind | sees | main noise filters (counted in `ctx.stats`) |
|---|---|---|
| `ais_gap` | silence longer than the threshold inside the covered area | left/re-entered the area, in port/at anchor, sparse reception, routine for this vessel, ordinary for its type |
| `loitering` | slow inside a small circle for a long time, away from port | moored whole time, waiting at port/anchorage, fishing on a fishing ground, habitual dwell cell |
| `rendezvous`, `cluster` | two vessels slow and close; N vessels gathered | learned stop areas; fishing-fleet discount; alerts above 6 vessels are split |
| `zone_entry` | entry into a protected zone (cable corridor, restricted waters) | routine visitors, transit discount |
| `position_jump`, `identity_conflict` | physically impossible movement, MMSI cloned | placeholder identities removed |
| `status_mismatch` | nav status contradicts movement | message-level data only |
| `route_deviation` | time in water normal traffic never uses | needs a traffic baseline |
| `dark_rendezvous` | one vessel goes dark while another stops where it could have reached | fleet-level grouping; fishing-majority discount |
| `cable_activity` | a vessel of ANY type (fishing included) slow or stopped on a charted cable, away from harbours, alone (a crowd of 6+ slow boats nearby = fishing ground, skipped); fixed objects (fish farms, buoys) excluded | 53 events / 37 vessels on the supplied day; first version, needs analyst review (`cableactivity.py`) |
| `survey_pattern` | repeated parallel/zig-zag legs (`survey.py`) | fishing/ferry/tug/pilot/SAR/service/dredger exempt, including fishing boats recognised by name |

**Identity hygiene (`identity.py`):** drift-net/trap beacons and placeholder identities (names such as `MJY06010-15-57%`, MMSIs outside
the valid 201-775 range) are dropped before detection. In the supplied full-day file ~2,700 of ~10,200 tracks were such non-ships.

**Survey-threat model (`threat.py`, `territory.py`, `declared.py`, `cables.py`)** - the mentor's factors plus what analysts read from
AIS. Output is the event kind `survey_threat`, whose `metrics.factors` object is what the UI renders as factor cards.

| factor | meaning | where |
|---|---|---|
| T territory | TS <= 12 nm, contiguous zone 12-24 nm, EEZ (approx. median-line, <= 200 nm), from public coastlines (not legal baselines) | `territory.py` |
| V velocity | share of fixes in the survey-speed band: **2-6 kn for message-level data** (measured on real research ships: median 4 kn in survey runs; 5-10 kn also holds 55% of their transit), 5-10 kn kept for hourly data | `config.py` |
| A AIS declaration | name (RESEARCH, SURVEY, KEXUE, XIANG YANG HONG ...), destination, registry subtype Research/Seismic Surveyor, nav status | `declared.py` |
| D destination | `TOWING KEEP 3NM CPA`, `TOWING 5NM CABLE`, `KEEP 2CPA PASSING`: towing a sensor array / cable work (score 0.95) | `declared.py` |
| N nav status | `RESTRICTED_MANEUVERABILITY` held at low speed; brief status switches while under way (rare: ~0.6% of non-fishing vessels) | `declared.py` |
| C cable proximity | share of the stretch within 10 nm of a charted submarine cable (TeleGeography public map, CC BY-NC-SA, approximate) | `cables.py` |
| P pattern | lawnmower / zig-zag legs | `survey.py` |

| rule | classification | severity |
|---|---|---|
| R7 | towing a survey array / slow manoeuvring survey work | 92 inside 24 nm, 80 in EEZ, 60 elsewhere; -8 if status only; +10 with a pattern |
| R2 | pattern inside territorial sea / contiguous zone | 85 (+5 declared, +5 speed) |
| R1 | declared survey vessel inside 24 nm (steaming through at transit speed drops to 58) | 78 TS / 70 CZ (+8 speed) |
| R3 / R4 | pattern in EEZ / declared at survey speed in EEZ | 72 / 62 |
| R5 | pattern outside Taiwan's claimed waters (behaviour only) | 55 |
| R6 | foreign state vessel (coast guard etc.) inside 12 nm | 70 |
| R0 | Taiwan-registered survey / towing vessel | 30, reported (low) so the analyst can see it |

Cable proximity adds +4 severity. Alert floors: R1/R2 inside 24 nm and R7 with severity >= 88 are raised to **HIGH**; towing announced
(R7 mode `tow`, severity >= 75, i.e. anywhere in the EEZ) is also raised to **HIGH**. Operator feedback can still lower them.

**Fusion (`alerts.py`):** risk = noisy-OR over the best event of each kind, weighted by kind and confidence; events on the same
vessels within the link window become one alert; fishing-type vessels are not discounted: routine behaviours of a fishing-majority group are merged into one area
summary per 0.25 degree cell and day; survey findings are never cut by the minimum-risk threshold; watch-list vessels (cited OSINT research-vessel list, OFAC SDN; matched on IMO/MMSI only) get +8 with a caveat.
Levels come from `alert_min_risk / medium_risk / high_risk`. Operator decisions (false alarm with reason, notes, allow-list)
down-weight or suppress similar alerts through `FeedbackStore` (`state.py`).

### 5. Machine-learning models

| model | file | what it is | measured |
|---|---|---|---|
| Isolation Forest + HistGradientBoosting second opinion (`ml.py`, `regionml.py`, `features.py`) | `data/models/ml_<region>.joblib` | 15 portable window features (reporting ratio, speed, radius, turning, implied speed, familiarity of water, stop-area share ...). Trained per region on history windows with injected behaviours as weak positives. Each alert gets `ml.agreement = agree / rules_only`, scores and the deviating features | Taiwan-GFW held-out days: rules flag 329 vessels (17 on added events); rules confirmed by the ML flag 99 (still 17) = ~74% fewer unverified alerts at no recall loss. GB ROC-AUC 0.99 is flattering (same generator as the tests); the robust finding is the confirmation filter |
| Region transfer test (`transfer.py`) | `transfer_models.joblib` | SF-trained model on Taiwan | does **not** transfer; train per region |
| Survey-shape classifier (`surveyml.py`) | `survey_shape.joblib` | learns zig-zag shapes from synthetic positives | experimental, **not used** (learned "synthetic vs real" shortcuts) |
| Path-analysis agent (`pathagent.py`, `scripts/evaluate_path_agent.py`) | none (rules + optional Claude) | advisory reviewer of slow windows of research-type vessels: research gate -> speed gate -> shape features -> category (survey lines under tow, lawnmower, station-keeping work, transit, port, drift, fishing, unclear) with reasons, caveats and a rendered picture; Claude version (`SEAWATCH_PATH_AGENT=claude`, `ANTHROPIC_API_KEY`) uses the same output format and falls back to the offline rules. Low-cost option: `SEAWATCH_PATH_AGENT=featherless` (`FEATHERLESS_API` in the environment or `.env`; model `SEAWATCH_FEATHERLESS_MODEL`, default Qwen2.5-7B-Instruct) adds a text-only language-model second reading of the flagged windows in the background; the rules keep the flag and the model only adjusts confidence and shows agreement or disagreement | On the five analyst-supplied examples (`data/labels/confirmed_paths.csv`): flags 3/5 vessels inside the marked +-12 h and 5/5 within +-36 h (the marked moment is often the fast leg between two working stretches); surfaces 7 other vessels (41 episodes in total) for review. Claude reviewer not run against the live API in this repo (no key); unit-tested with a stub |
| Path-shape model (`pathml.py`, `scripts/train_path_model.py`) | none saved | stage 1 slow-vessel filter (1.5-7 kn median, >= 8 nm path), 17 path-only features, weak labels from announced towing / restricted status | **not usable yet**: 21 windows on 9 vessels, vessel-grouped ROC-AUC 0.45; speed steadiness alone 0.68. Trained models are only worth trusting once confirmed tracks exist (`data/labels/confirmed_paths.csv` overrides the weak labels) |

Real-outcome checks (`realoutcomes.py`, `docs/real-outcomes.md`): behaviour rules do not separate OFAC-sanctioned vessels (AUC ~0.49;
a listing is about the hull, not the week's behaviour), and identity screening is no better than flag + ship type. The reported
PRC research vessels (Heritage BG3977 Table 2, `data/labels/osint_vessels.csv`) are used as a watch-list, not as training labels.

### 6. API contract the UI uses (`/detection/*`, interactive docs at `/docs`)

| endpoint | purpose |
|---|---|
| `GET /regions`, `POST /region {id}` | list and switch regions |
| `GET /scenario` | name, time range, zones, receivers, `data_kind`, `timezone`, bounds |
| `GET /tracks` | tracks for the map (large feeds are sampled to ~2,500 incl. every alerted vessel) |
| `GET /alerts?as_of=&include_dismissed=` | risk-ranked alert summaries (`id, title, risk, level, confidence, vessels, kinds, status, ml_agreement, top_reason ...`); `as_of` is the replay clock |
| `GET /alerts/{id}` | detail: `reasons[]`, `breakdown[]` (points per kind), `benign_explanations[]`, `uncertainty[]`, `recommended_action`, `ml`, `watch[]`, `timeline[]` (events with `evidence[]`, `metrics`, `path`) |
| `POST /alerts/{id}/status`, `POST /alerts/{id}/notes`, `POST /allowlist`, `POST /feedback/reset` | operator workflow |
| `GET/PUT /config`, `POST /config/reset` | thresholds with units/ranges/help text (`specs`), values, defaults; alerts recompute |
| `GET /evaluation`, `GET /truth`, `GET /ml` | measured accuracy against labels (simulated / injected regions), the labels, ML benchmark |
| `GET /assessment` | signal-vs-noise: funnel (vessels -> events -> alerts -> HIGH), per-detector discards with reasons, factor combination table, classifications, top survey-threat vessels |
| `GET /rulebook` | every rule with live thresholds, innocent explanations and limits |
| `GET /path-reviews`, `GET /path-reviews/{id}/image`, `POST /path-reviews/{id}/decision`, `GET /path-reviews-export` | path-agent reviews (advisory), the picture it looked at, analyst accept / reject, accepted / rejected rows for `confirmed_paths.csv`. Alert detail also carries `path_reviews[]` |
| `GET /layers` | GeoJSON for cables, landing points and the 12 nm / 24 nm / EEZ limit lines |

For a `survey_threat` event, `metrics` contains `classification`, `rule` (R0-R7), `transit`, `mode`, and `factors` with keys
`territory, velocity, declared, status, towing, cable, pattern, foreign, state_class`, each with `met` and the numbers behind it.
UI components already built: `AlertQueue`, `AlertPanel` (+ `FactorCards`), `WatchMap` (layers: cables, limits, zones, tracks, coverage),
`ReplayBar`, `TuningLab`, `Insight` (Assessment + Rulebook views). All are in `apps/web/src/features/watch/`; the typed client is `api.ts`.

### 7. Data and scripts

| need | command |
|---|---|
| SF Bay real data | `python scripts/setup_sfbay_data.py` |
| Taiwan hourly (GFW) | set `SEAWATCH_DATA_ROOT` (drive with `SeaWatch\ais\historical\processed\daily`); first start caches to `data/processed/tw_gfw_cache.pkl`, which the app then runs from even with the drive unplugged |
| Hackathon-supplied April 2026 Taiwan AIS | `python scripts/build_taiwan_ais.py DAY.csv RESEARCH_01.csv RESEARCH_02.csv` -> `taiwan-day`, `taiwan-research` |
| Any new AIS export | `python scripts/ingest_mentor_ais.py PATH` (guesses columns, decides hourly vs message-level, learns on the first 80%, reports on the last 20%) |
| Map layers | `python scripts/build_cables.py`, `python scripts/build_zone_lines.py`, `python scripts/build_taiwan_geo.py` (downloads noted in each script) |
| ML | `scripts/train_region_ml.py` (SF), `scripts/train_tw_ml.py` (Taiwan hourly), `scripts/train_path_model.py` (experimental) |
| Measurements | `tune_tw.py`, `tune_sf.py`, `evaluate_rules_on_real.py`, `analyse_research_vessels.py`, `analyse_day.py`, `evaluate_real_outcomes.py` |
| Regenerate the rulebook | `python -c "from apps.api.seawatch.detection.rulebook import render_markdown; open('docs/rulebook.md','w',encoding='utf8').write(render_markdown())"` |

Licences/limits: cable routes are TeleGeography (CC BY-NC-SA 4.0, non-commercial) and approximate; zone lines are modelled from
Natural Earth coastlines (public domain), not legal baselines; the GFW, OFAC and Heritage data keep their own terms.

### 8. Known limits (read before integrating)

- Gap / loitering / rendezvous / cluster detection is not offered in the Taiwan regions (see section 3); fix it first in `sf-bay`, where it can be measured.
- Recall on added events in the hourly region at the default threshold: clusters 3/3 and zone entries 6/6, but dark gaps 3/15, loitering
  0/15, rendezvous 0/3, survey patterns 5/15. These need work before they are demoed as strengths.
- The research files carry no event labels; "Research" is a registry class, not proof of survey work or intent.
- The simulated-region alert for the towing ship draws the whole track; the survey legs should be highlighted (UI task).
- Two unrelated tests in `tests/unit/test_web_serving.py` fail on the installed FastAPI version (route objects have no `.path`); they
  fail without these changes too.

### 9. Planned next

1. **Path-analysis agent: built (offline rules + Claude reviewer); next** is running the Claude reviewer with a key, comparing it with the
   offline rules on the five confirmed examples, and growing the confirmed set from analyst accept / reject decisions.
2. **Integration with the live SeaWatch system:** see `docs/integration-answers.md` (entry point `engine.analyze`, capability gating,
   `redact()` for public ids, runtimes, open items). Review of the full rule set is the step before that.
3. **Confirmed tracks.** Obtain confirmed illegal-research tracks and matched ordinary slow tracks (fishing, tugs, cable ships) from
   the mentor/OSINT; load them through `data/labels/confirmed_paths.csv`; retrain `pathml` and report vessel-grouped accuracy. Until then
   the learned path model stays out of the alert score.
4. **Longer message-level history** for Taiwan to learn per-vessel routines and cut the `taiwan-day` noise; re-measure with the funnel.
5. **UI work:** highlight the survey legs of the selected `survey_threat` event on the map, show the filtered slow-window candidates,
   and add an agent-review panel with accept/reject.
6. **Official geometry:** replace the modelled territorial/EEZ lines and the public cable routes with official data when available.
7. **Sensors beyond AIS** (SAR, RF) for vessels that go dark, as an extension of `dark_rendezvous`.

---

## Development Status

### Completed

- ✅ NOAA AIS data foundation
- ✅ GeoParquet ingestion pipeline
- ✅ Trajectory segmentation
- ✅ Geodesic movement features
- ✅ Multi-day AIS cohort preparation
- ✅ Explainable anomaly ranking baseline
- ✅ Statistical baseline comparison

### Added since (see "Detection stack and hand-off guide")

- ✅ Rule detectors, fusion into risk-ranked alerts, operator feedback
- ✅ Taiwan survey-threat model (territory, speed, AIS declaration, towing text, nav status, cables, pattern)
- ✅ ML second opinion per region, honest real-outcome checks
- ✅ Watch Floor dashboard, tuning lab, rulebook and assessment views
- ✅ Real Taiwan AIS regions (hourly presence and message-level April 2026)

### Current

- 🚧 Path-analysis agent and confirmed-track training data (planned next)

### Future

- ⏳ Emergency logistics simulation
- ⏳ Edge deployment exploration

---

## Roadmap

### Phase 1 — Data Foundation ✅

- Official AIS data acquisition
- Data validation and provenance tracking
- Reproducible preprocessing

### Phase 2 — Trajectory Intelligence ✅

- Track segmentation
- Time-window generation
- Movement feature engineering

### Phase 3 — Explainable Ranking 🚧

- Behavior deviation ranking
- Statistical baseline evaluation
- Explainable alert generation

### Phase 4 — Decision Dashboard ⏳

- Interactive maritime map
- Track investigation interface
- Human feedback workflow

### Phase 5 — Resilience Extension ⏳

- Emergency logistics simulation
- Disruption scenario analysis

---

## Research Principles

- Explainability over black-box prediction
- Human review over autonomous decisions
- Reproducibility over hidden pipelines
- Decision support over automated judgement

---

## Project Structure

```text
seawatch/
├── apps/
│   ├── api/seawatch/detection/   detectors, threat model, ML, regions
│   ├── api/seawatch/api/         HTTP routes (/detection, /resilience)
│   └── web/src/features/watch/   Watch Floor UI
├── data/                         geo layers, labels, processed caches, models
├── scripts/                      data builders, training, measurements
├── models/
├── tests/
├── docs/
└── experiments/
```

---

## Project Status

SeaWatch is an active research and development project. The data foundation and
trajectory intelligence and offline review-ranking layers are complete. The
decision dashboard, human review workflow, and resilience extension remain
planned stages.

### Phase 3B documentation

- [Offline review-ranking runbook](docs/phase3b-review-ranking-runbook.md)
- [Measured baseline comparison](docs/phase3b-baseline-comparison-report.md)
- [Design specification](docs/superpowers/specs/2026-09-30-phase3b-explainable-review-ranking-design.md)
- [Implementation plan](docs/superpowers/plans/2026-09-30-phase3b-explainable-review-ranking.md)

### Phase 8 Edge resilience

- [Edge AIS operations](docs/edge-ais-runbook.md)
- [Offline map installation](docs/offline-map.md)
- [Offline localhost startup](docs/offline-startup-runbook.md)
- [Verification and measurements](docs/phase8-edge-resilience-report.md)

Phase 8 adds opt-in local AIS reception, honest Cloud/Edge/replay modes,
same-origin localhost production serving, and a fully bundled emergency map.
Cloud remains the default deployment and local web serving remains disabled
unless `SEAWATCH_SERVE_WEB=true`.

### Phase 9 Resilience Logistics (RESPOND)

- [Resilience demo runbook](docs/phase9-resilience-logistics-runbook.md)
- [Verification report](docs/phase9-resilience-logistics-report.md)
- [Design specification](docs/superpowers/specs/2026-10-01-resilience-logistics-design.md)
- [Implementation plan](docs/superpowers/plans/2026-10-01-resilience-logistics-implementation-plan.md)

Phase 9 adds the **RESPOND** layer: a deterministic, explainable
decision-support simulation for a civilian port-disruption scenario (affected
demand, alternative ports/routes, priority-aware capacity-constrained
allocation, trade-offs, and a bilingual Resilience Decision Brief). It is for
**human review only** — not an instruction, prediction, or autonomous command.
Capacity, cost, risk, and demand figures are `scenario`/`synthetic` planning
values, never real operational data, and an always-visible TruthBadge preserves
that provenance. Phase 9 adds no new dependency, reuses the Phase 8 shared API
client and offline map machinery, and consumes Phase 8 only through the stable,
read-only `/resilience/status` contract. The SENSE → SURVIVE → RESPOND
demonstration runs fully offline; the live-RF Edge hardware path remains
**pending real-hardware validation**.
