# SeaWatch Phase 3A NOAA AIS Multi-Day Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the approved 2024-01-02 and 2024-01-03 NOAA AIS sources to a reproducible three-date, date-split corpus without changing Phase 2 features or implementing anomaly logic.

**Architecture:** Keep ingestion and feature generation physically independent per date, then build one aggregate cohort manifest that references the daily artifacts by path and hash and assigns fixed train/calibration/test roles. Parameterize the existing CLIs from a strict three-date catalog; keep all automated tests offline and reserve network access for two explicit smoke commands.

**Tech Stack:** Python 3.12.7, pandas 3.0.6, NumPy 2.5.3, PyArrow 25.0.1, pyproj 3.8.0, pytest 9.1.1, JSON manifests, Parquet/GeoParquet.

**Spec:** `docs/superpowers/specs/2026-09-30-noaa-ais-multiday-expansion-design.md`

## Global Constraints

- Start from exact commit `d0bdd977989a3ff74f9aa0ff9760685123f1f4a9` on a local `feat/multiday-data-expansion` branch unless the user selects another branch name.
- Use the existing project `.venv` created with `C:\wu\python.exe`; do not modify global Python.
- Download only 2024-01-02 and 2024-01-03 during Phase 3A execution. Reuse the existing January 1 artifacts.
- Do not silently substitute another date when a source is missing or incompatible.
- Keep `config/noaa_ais_2024_columns.json` and `config/trajectory_features_v1.json` semantically unchanged.
- Preserve complete chronological track histories. The 50,000-observation value is a per-date maximum ceiling, not a quota.
- Process every date independently through the existing ingestion, segmentation, window, and feature contracts. Never make a cross-date segment or window.
- The fixed roles are January 1 train/reference, January 2 calibration, and January 3 test/holdout.
- Raw identifiers may exist only in ignored/local source processing. Public/debug schemas and aggregate documents fail closed on forbidden identifiers.
- Raw NOAA files, processed Parquet, previews, `.venv`, secrets, databases, caches, and model artifacts remain ignored and uncommitted.
- Tests perform no network access. Real NOAA work is an explicit smoke workflow.
- Do not implement anomaly detection, Isolation Forest, rules, model fitting/scoring, API, UI, logistics, persistence, cloud, hardware, or deployment.
- Stop and report before adapting if observed license, source schema, CRS, geometry, timestamp/date semantics, or geographic subset materially differs from the validated contract.

## Review Focus

- Catalog date/URL mismatch or an unapproved fourth date must fail before network or filesystem writes; Task 1 and Task 2 tests pin this behavior.
- Source timestamps outside the catalog UTC date must fail rather than leak into another split; Task 3 tests pin this behavior.
- A daily configuration, CRS, schema, hash, or split-role mismatch must block cohort publication; Task 4 tests pin this behavior.
- Dates/tracks/segments with zero feature windows must remain present in zero-inclusive QA distributions; Task 4 tests pin this behavior.
- Final, `.partial`, input, and output path aliases or incomplete daily lineages must fail before writes; Task 5 tests pin this behavior.

---

### Task 1: Strict Phase 3A source and split catalog

**Files:**
- Create: `config/noaa_ais_phase3a_dates.json`
- Create: `apps/api/seawatch/datasets/__init__.py`
- Create: `apps/api/seawatch/datasets/source_catalog.py`
- Create: `tests/unit/test_source_catalog.py`

**Interfaces:**
- Produces: `ApprovedDailySource(date: datetime.date, source_url: str, raw_filename: str, split_role: Literal["train", "calibration", "test"])`.
- Produces: `Phase3ACatalog(schema_version: str, entries: tuple[ApprovedDailySource, ...])`.
- Produces: `load_phase3a_catalog(path: Path) -> Phase3ACatalog`.
- Produces: `Phase3ACatalog.for_date(source_date: date) -> ApprovedDailySource`.
- Consumes later: Tasks 2-5 use only these catalog objects for source selection and split assignment.

- [ ] **Step 1: Write failing catalog tests**

  Assert the committed catalog contains exactly `2024-01-01`, `2024-01-02`,
  and `2024-01-03` in chronological order; URLs end in the matching daily
  Parquet name; filenames match; and roles are train, calibration, test.
  Parameterize rejection tests for a fourth date, duplicate date/role, missing
  role, URL/date mismatch, unknown key, non-HTTPS URL, and wrong schema version.

- [ ] **Step 2: Run the catalog tests and verify RED**

  Run: `& '.\.venv\Scripts\python.exe' -m pytest tests/unit/test_source_catalog.py -v`

  Expected: FAIL because `source_catalog` and the catalog file do not exist.

- [ ] **Step 3: Implement the catalog contract**

  Validate the complete JSON object, exact date set, one occurrence of each
  role, chronological order, HTTPS host/path, date embedded in URL/filename,
  and no extra entries. `for_date` raises `ValueError` for an unapproved date.

- [ ] **Step 4: Run tests and verify GREEN**

  Run: `& '.\.venv\Scripts\python.exe' -m pytest tests/unit/test_source_catalog.py -v`

  Expected: all catalog tests pass.

- [ ] **Step 5: Commit Task 1**

  ```powershell
  git add config/noaa_ais_phase3a_dates.json apps/api/seawatch/datasets/__init__.py apps/api/seawatch/datasets/source_catalog.py tests/unit/test_source_catalog.py
  git commit -m "feat: define approved NOAA multi-day catalog"
  ```

### Task 2: Catalog-bound daily download CLI

**Files:**
- Modify: `scripts/download_noaa_ais.py`
- Modify: `tests/unit/test_noaa_ais.py`
- Modify: `tests/integration/test_prepare_cli.py`

**Interfaces:**
- Consumes: `load_phase3a_catalog` and `Phase3ACatalog.for_date` from Task 1.
- Produces: CLI option `--date YYYY-MM-DD`, default `2024-01-01` for backward compatibility.
- Produces: derived default destination `data/raw/ais-<date>.parquet`; an explicit destination remains testable but never changes the approved source URL.
- Preserves: the existing `--url` option only as a strict assertion; when supplied, it must exactly equal the selected catalog URL or fail before transport/writes.
- Preserves: `download_file`, `write_download_record`, atomic partial writes, hash/length/timestamp sidecar, and explicit `--force`.

- [ ] **Step 1: Extend tests before production changes**

  Add mocked-transport tests proving January 2 and January 3 resolve to their
  exact catalog URLs/destinations. Assert January 4 and URL/date mismatch fail
  before transport is called or a file is written. Retain January 1 regression
  expectations. Patch all network calls; no test may access NOAA.

- [ ] **Step 2: Run focused tests and verify RED**

  Run: `& '.\.venv\Scripts\python.exe' -m pytest tests/unit/test_noaa_ais.py tests/integration/test_prepare_cli.py -k 'date or approved or download' -v`

  Expected: new date-selection tests fail because the CLI is January-1-only.

- [ ] **Step 3: Parameterize the CLI from the catalog**

  Load the committed catalog, parse the ISO date strictly, select the exact
  entry, derive the destination only after validation, then call the existing
  downloader. Keep the January 1 no-argument behavior documented and green.

- [ ] **Step 4: Run focused and Phase 1 download tests**

  Run: `& '.\.venv\Scripts\python.exe' -m pytest tests/unit/test_noaa_ais.py tests/integration/test_prepare_cli.py -v`

  Expected: all pass with mocked network transport.

- [ ] **Step 5: Commit Task 2**

  ```powershell
  git add scripts/download_noaa_ais.py tests/unit/test_noaa_ais.py tests/integration/test_prepare_cli.py
  git commit -m "feat: parameterize approved NOAA daily downloads"
  ```

### Task 3: Date-aware Phase 1 preparation without contract changes

**Files:**
- Modify: `scripts/prepare_smoke_dataset.py`
- Modify: `apps/api/seawatch/trajectories/preprocess.py`
- Modify: `tests/unit/test_preprocess.py`
- Modify: `tests/integration/test_prepare_cli.py`
- Modify: `tests/integration/test_smoke_pipeline.py`

**Interfaces:**
- Consumes: Task 1 catalog and existing `prepare_smoke_dataset_batches`, `build_manifest`, Parquet/preview writers.
- Produces: CLI option `--source-date YYYY-MM-DD`, default `2024-01-01`.
- Produces: `validate_source_date_range(minimum: pd.Timestamp, maximum: pd.Timestamp, source_date: date) -> None` in `preprocess.py`.
- Preserves: exact eight-column public schema, SF Bay bbox, cargo codes 70-79, complete-track selection, source-date-salted surrogate IDs, and the 50,000 maximum.

- [ ] **Step 1: Write date and complete-history regression tests**

  Test January 2 and January 3 manifest IDs/paths, timestamp confinement to
  `[date 00:00:00Z, next date 00:00:00Z)`, download-record URL/date matching,
  and failure before writes for out-of-date observations. Prove the same raw
  source identifier maps to different deterministic surrogates on two dates.
  Construct a ceiling fixture where the next whole track would exceed the
  maximum and assert that track is excluded whole, never truncated or sampled.

- [ ] **Step 2: Run focused tests and verify RED**

  Run: `& '.\.venv\Scripts\python.exe' -m pytest tests/unit/test_preprocess.py tests/integration/test_prepare_cli.py tests/integration/test_smoke_pipeline.py -k 'date or ceiling or surrogate' -v`

  Expected: new source-date tests fail.

- [ ] **Step 3: Implement catalog date validation and parameterization**

  Replace the single approved URL constant with the selected catalog entry.
  Derive the source date used by `build_manifest` and surrogate generation from
  the validated CLI date. Validate observed timestamp bounds before publishing
  outputs. Do not change filtering, deduplication, selection, or schema logic.

- [ ] **Step 4: Run all Phase 1 tests**

  Run: `& '.\.venv\Scripts\python.exe' -m pytest tests/unit/test_preprocess.py tests/unit/test_noaa_ais.py tests/integration/test_prepare_cli.py tests/integration/test_smoke_pipeline.py -v`

  Expected: all existing and new Phase 1 tests pass.

- [ ] **Step 5: Commit Task 3**

  ```powershell
  git add scripts/prepare_smoke_dataset.py apps/api/seawatch/trajectories/preprocess.py tests/unit/test_preprocess.py tests/integration/test_prepare_cli.py tests/integration/test_smoke_pipeline.py
  git commit -m "feat: prepare approved NOAA dates independently"
  ```

### Task 4: Multi-day lineage, split, and QA manifest builder

**Files:**
- Create: `apps/api/seawatch/datasets/multiday_manifest.py`
- Create: `tests/unit/test_multiday_manifest.py`

**Interfaces:**
- Consumes: `Phase3ACatalog`, daily Phase 1 manifests, daily Phase 2 manifests, and referenced local artifacts.
- Produces: `DailyLineage(source_date: date, split_role: str, phase1_manifest_path: Path, feature_manifest_path: Path)`.
- Produces: `load_daily_lineage(entry: ApprovedDailySource, phase1_manifest_path: Path, feature_manifest_path: Path, *, root: Path) -> DailyLineage`.
- Produces: `build_phase3a_manifest(catalog: Phase3ACatalog, lineages: Sequence[DailyLineage]) -> dict[str, object]`.
- Produces: `render_phase3a_report(manifest: Mapping[str, object]) -> str`.
- Produces schema version: `phase3a-multiday-v1`.

- [ ] **Step 1: Write failing lineage validation tests**

  Build three tiny synthetic daily manifest/artifact sets. Assert exact split
  membership, chronological order, shared column-map/config hashes, aggregate
  totals, rejection reasons, zero-inclusive windows-per-track/segment metrics,
  feature missingness, quantiles, accepted-window concentration, nominal
  overlap factor, and approximate non-overlapping-window count.

  Parameterize hard failures for missing/duplicate/unapproved dates, changed
  role, daily timestamp spill, schema/CRS/timezone mismatch, feature config
  mismatch, source/manifest/artifact hash mismatch, missing artifact, forbidden
  public column, and a date referenced by two roles. Include a date with zero
  windows and assert it remains in the report with zeros and null quantiles.

- [ ] **Step 2: Run unit tests and verify RED**

  Run: `& '.\.venv\Scripts\python.exe' -m pytest tests/unit/test_multiday_manifest.py -v`

  Expected: FAIL because the multi-day module does not exist.

- [ ] **Step 3: Implement strict daily lineage loading**

  Resolve paths against `root`, verify recorded size/hash/schema metadata and
  source/config lineage, and retain aggregate-only data. Never copy raw IDs or
  row-level observations into the cohort payload.

- [ ] **Step 4: Implement aggregate manifest and Markdown report**

  Use the fixed catalog roles; sum counts only when additive, compute
  zero-inclusive per-date metrics, emit measured cross-date deltas, and include
  Gate A/B evidence without behavioral labels. Handle empty distributions as
  `null`/`not measured`, never zero-filled values.

- [ ] **Step 5: Run tests and verify GREEN**

  Run: `& '.\.venv\Scripts\python.exe' -m pytest tests/unit/test_multiday_manifest.py -v`

  Expected: all lineage, aggregation, privacy, and empty-date tests pass.

- [ ] **Step 6: Commit Task 4**

  ```powershell
  git add apps/api/seawatch/datasets/multiday_manifest.py tests/unit/test_multiday_manifest.py
  git commit -m "feat: build date-isolated AIS cohort manifests"
  ```

### Task 5: Offline Phase 3A cohort CLI

**Files:**
- Create: `scripts/build_phase3a_cohort.py`
- Create: `tests/integration/test_phase3a_cohort_cli.py`

**Interfaces:**
- Consumes: Task 1 catalog and Task 4 lineage/manifest/report functions.
- Default inputs: the three date-specific Phase 1/2 manifests and their referenced artifacts.
- Default outputs: `data/manifests/noaa_ais_2024-01-01_to_2024-01-03_sf_bay_phase3a.json` and `docs/phase3a-data-expansion-report.md`.
- Produces no raw, processed, preview, segment, or feature data and performs no network access.
- Supports explicit `--force` only after final/partial/input/output alias preflight.

- [ ] **Step 1: Write failing end-to-end CLI tests**

  Create three synthetic daily lineages and assert the CLI writes an atomic
  cohort manifest/report with exact roles and aggregates. Assert all output
  collisions and `.partial`/input aliases fail before reads or writes. Patch
  network libraries to raise if touched. Test missing January 3, mismatched
  config hash, and malformed daily JSON leave no final or partial output.

- [ ] **Step 2: Run integration tests and verify RED**

  Run: `& '.\.venv\Scripts\python.exe' -m pytest tests/integration/test_phase3a_cohort_cli.py -v`

  Expected: FAIL because the cohort CLI does not exist.

- [ ] **Step 3: Implement the offline CLI**

  Parse catalog/root/input/output paths, preflight every write target, load all
  three lineages, build the aggregate payload/report, and replace `.partial`
  files atomically only after both render successfully.

- [ ] **Step 4: Run cohort and regression tests**

  Run: `& '.\.venv\Scripts\python.exe' -m pytest tests/unit/test_source_catalog.py tests/unit/test_multiday_manifest.py tests/integration/test_phase3a_cohort_cli.py -v`

  Expected: all pass with zero network access.

- [ ] **Step 5: Commit Task 5**

  ```powershell
  git add scripts/build_phase3a_cohort.py tests/integration/test_phase3a_cohort_cli.py
  git commit -m "feat: add offline Phase 3A cohort workflow"
  ```

### Task 6: Reproducible runbook and synthetic three-date contract

**Files:**
- Create: `docs/phase3a-data-expansion-runbook.md`
- Modify: `README.md`
- Create: `tests/integration/test_phase3a_synthetic_pipeline.py`

**Interfaces:**
- Consumes all Task 1-5 public interfaces and the unchanged Phase 1/2 pipelines.
- Produces documented PowerShell commands for only January 2 and January 3 acquisition, per-date preparation/features, cohort publication, and audits.

- [ ] **Step 1: Write a synthetic three-date integration test**

  Flow three small date-confined datasets through preparation, segmentation,
  windows, and features, then build the cohort. Assert no segment/window spans
  dates, January 1/2/3 map only to train/calibration/test, the same Phase 2
  configuration hash appears three times, no feature definition changes, and
  no forbidden identifiers or private membership reach public artifacts.

- [ ] **Step 2: Run the integration test and verify its initial result**

  Run: `& '.\.venv\Scripts\python.exe' -m pytest tests/integration/test_phase3a_synthetic_pipeline.py -v`

  Expected: FAIL at the first missing multi-date wiring contract, or PASS if
  Tasks 1-5 already supply the complete interface. Do not invent a change for
  an unexpected pass.

- [ ] **Step 3: Make only required wiring corrections**

  Correct imports, path derivation, or deterministic ordering. Do not alter
  Phase 2 feature definitions or weaken validation to satisfy the fixture.

- [ ] **Step 4: Write the runbook and README section**

  Document separate download commands for January 2 and January 3, actual-file
  inspection and discrepancy stops, explicit Phase 1 and Phase 2 output paths,
  cohort building, ignored-artifact behavior, privacy checks, and full tests.
  State that no command downloads January 1 or any fourth date automatically.

- [ ] **Step 5: Run the complete offline suite**

  Run: `& '.\.venv\Scripts\python.exe' -m pytest -q`

  Expected: all Phase 1, Phase 2, and synthetic Phase 3A tests pass with no
  network access.

- [ ] **Step 6: Commit Task 6**

  ```powershell
  git add docs/phase3a-data-expansion-runbook.md README.md tests/integration/test_phase3a_synthetic_pipeline.py
  git commit -m "docs: define reproducible multi-day AIS workflow"
  ```

### Task 7: Explicit January 2 and January 3 NOAA smoke workflow

**Files:**
- Create after measurement: `data/manifests/noaa_ais_2024-01-02_sf_bay.json`
- Create after measurement: `data/manifests/noaa_ais_2024-01-02_sf_bay_trajectory_features.json`
- Create after measurement: `data/manifests/noaa_ais_2024-01-03_sf_bay.json`
- Create after measurement: `data/manifests/noaa_ais_2024-01-03_sf_bay_trajectory_features.json`
- Create after measurement: `data/manifests/noaa_ais_2024-01-01_to_2024-01-03_sf_bay_phase3a.json`
- Create after measurement: `docs/qa/noaa-ais-2024-01-02-data-foundation.md`
- Create after measurement: `docs/qa/noaa-ais-2024-01-02-trajectory-features.md`
- Create after measurement: `docs/qa/noaa-ais-2024-01-03-data-foundation.md`
- Create after measurement: `docs/qa/noaa-ais-2024-01-03-trajectory-features.md`
- Create after measurement: `docs/phase3a-data-expansion-report.md`

**Interfaces:**
- Consumes local network only for the two approved download commands.
- Produces ignored daily raw/inspection/processed/preview/feature artifacts and committed aggregate manifests/reports.

- [ ] **Step 1: Verify the existing January 1 lineage without downloading it**

  Run the Phase 1 smoke integration test, Phase 2 real audit, and source/output
  hash checks. Stop if the validated baseline is missing or altered.

- [ ] **Step 2: Download and inspect January 2 only**

  Run the catalog-bound download command with `--date 2024-01-02`, inspect the
  actual artifact, and compare observed publisher/license/schema/GeoParquet
  CRS/geometry/date coverage with January 1. If materially incompatible, stop
  and report; do not download January 3 or adapt scope silently.

- [ ] **Step 3: Prepare January 2 Phase 1 and Phase 2 outputs**

  Use explicit date-specific source, sidecar, processed, preview, manifest,
  report, segmented, segment-summary, window, feature-manifest, and
  feature-report paths. Use the unchanged column map and feature config. Record
  measured values; do not force January 1 counts.

- [ ] **Step 4: Download and inspect January 3 only**

  Repeat Step 2 for `2024-01-03`. Stop on material discrepancy and do not
  acquire any replacement date.

- [ ] **Step 5: Prepare January 3 Phase 1 and Phase 2 outputs**

  Repeat Step 3 with January 3 paths and unchanged configuration.

- [ ] **Step 6: Build the cohort manifest and report**

  Run `scripts/build_phase3a_cohort.py --force`. Report actual per-date and
  total counts, rejections, missingness, distributions, concentration,
  effective non-overlapping counts, comparability checks, and Gate A/B. Do not
  label movement extremes as anomalies.

- [ ] **Step 7: Independently audit real outputs read-only**

  Recompute daily and cohort hashes/counts/schemas/config hashes/splits,
  timestamp bounds, segment/window date boundaries, feature finiteness,
  aggregate totals, and report/manifest agreement. Confirm January 1 was not
  downloaded and no fourth date exists.

- [ ] **Step 8: Confirm privacy and ignored-artifact behavior**

  Use `git check-ignore` on all new raw/processed/preview/feature artifacts;
  scan committed manifests/reports for direct identifier names or values; and
  verify aggregate documents contain no individual `track_id` values.

- [ ] **Step 9: Commit measured aggregate metadata only**

  Stage the five manifests and five reports listed above only after every real
  audit passes. Do not stage generated Parquet/GeoJSON, raw data, sidecars, or
  inspection outputs.

  ```powershell
  git commit -m "docs: record measured three-date AIS cohort"
  ```

### Task 8: Final regression, scope, and Phase 3B readiness audit

**Files:**
- Modify only files required to correct a verified failure.

**Interfaces:**
- Verifies the complete Phase 3A branch and introduces no model behavior.

- [ ] **Step 1: Run full tests, compilation, and CLI help**

  ```powershell
  & '.\.venv\Scripts\python.exe' -m pytest -q
  & '.\.venv\Scripts\python.exe' -m compileall -q apps scripts
  & '.\.venv\Scripts\python.exe' scripts/download_noaa_ais.py --help
  & '.\.venv\Scripts\python.exe' scripts/prepare_smoke_dataset.py --help
  & '.\.venv\Scripts\python.exe' scripts/prepare_trajectory_features.py --help
  & '.\.venv\Scripts\python.exe' scripts/build_phase3a_cohort.py --help
  ```

  Expected: all tests pass; commands exit 0; pytest performs no network calls.

- [ ] **Step 2: Repeat the independent real cohort audit**

  Recompute all committed aggregate values from the existing local artifacts.
  Verify exact split membership, identical configuration hashes, no date
  crossing, and the report's Gate A/B evidence.

- [ ] **Step 3: Audit forbidden scope and content**

  Search implementation changes for anomaly/model/rule logic, Isolation
  Forest, API routes, frontend/MapLibre, SQLite, logistics, hardware, cloud,
  deployment, secrets, identifiers, and binary/model artifacts. Documentation
  may name explicit exclusions; executable behavior may not implement them.

- [ ] **Step 4: Audit Git and staged files explicitly**

  Run `git status --short`, `git diff --check`, staged name/size/numstat checks,
  `git check-ignore` for generated artifacts, `git log` from `d0bdd97`, and
  `git remote -v`. Confirm no generated raw/processed/preview/feature data is
  tracked and no remote/push occurred unless separately authorized.

- [ ] **Step 5: Apply the Phase 3B gate exactly**

  Choose only:

  - `A. DATA SUFFICIENT FOR BASELINE ANOMALY EXPERIMENTS`, if every criterion
    in design section 13 passes; or
  - `B. NEED ADDITIONAL DATA INVESTIGATION`, naming each failed criterion.

  Do not implement an experiment under either result. Under B, recommend an
  investigation but do not download any date beyond January 3.

- [ ] **Step 6: Record final evidence and stop**

  Report starting SHA, branch, changed files, two acquired source hashes/sizes,
  per-date/total observations/tracks/segments/windows/rejections, missingness,
  cross-date QA, split audit, generated ignored artifact sizes, test results,
  privacy/Git audit, commit SHAs, final status, and Gate A/B. Stop before Phase
  3B modeling.
