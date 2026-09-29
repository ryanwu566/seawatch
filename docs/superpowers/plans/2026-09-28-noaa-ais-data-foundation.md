# NOAA AIS Data Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and verify a reproducible Phase 1 pipeline that acquires the official NOAA 2024-01-01 AIS GeoParquet, inspects its actual schema, produces a provenance-preserving SF Bay cargo-vessel smoke dataset, and records measured QA.

**Architecture:** A source adapter owns deterministic download, hashing, and Parquet/GeoParquet inspection. A pure trajectory-preprocessing module owns schema normalization, validation, filtering, ordering, deduplication, surrogate IDs, complete-track selection, outputs, and QA statistics; thin CLI scripts orchestrate these functions for the real dataset.

**Tech Stack:** Python 3.12.7 from `C:\wu\python.exe`, project-local `.venv`, pandas, NumPy, PyArrow, Shapely, PyProj, pytest, standard-library HTTP and hashing.

**Spec:** `docs/superpowers/specs/2026-09-28-noaa-ais-data-foundation-design.md`

## Global Constraints

- Work only on local branch `feat/data-gis-foundation`; do not add a remote or push.
- Create `.venv` with exactly `C:\wu\python.exe -m venv .venv`; do not modify global Python.
- Use only the official source URL `https://ocmgeodatastor1.blob.core.windows.net/marinecadastre/ais2024/ais-2024-01-01.parquet`.
- Verify the source documentation and observed license before writing them to the manifest.
- Do not substitute another source if the official source is unavailable.
- Do not commit real raw AIS, generated processed Parquet, or generated GeoJSON.
- Commit only code, tests, manifests, measured reports, provenance documentation, and tiny synthetic test fixtures.
- Treat 50,000 observations as a maximum, not a quota; never truncate or randomly sample individual observations to reach it.
- Preserve complete chronological vessel histories in selected output.
- Never display or write raw MMSI/source vessel identifiers to the preview GeoJSON or public processed columns.
- Do not infer identity, intent, hostility, or anomalous behavior.
- Do not interpolate gaps or discard unusual motion.
- Add no ML, API, frontend, database, live AIS, authentication, challenge #10, deployment, or container work.
- Create exactly one final local commit named `feat: establish NOAA AIS data foundation`; create no intermediate commits.

## File Map

- Create `apps/api/seawatch/__init__.py`: package marker only.
- Create `apps/api/seawatch/adapters/__init__.py`: adapter package marker.
- Create `apps/api/seawatch/adapters/noaa_ais.py`: download, SHA-256, transfer record, Parquet/GeoParquet inspection.
- Create `apps/api/seawatch/trajectories/__init__.py`: trajectory package marker.
- Create `apps/api/seawatch/trajectories/preprocess.py`: canonicalization, validation, filters, ordering, deduplication, IDs, track selection, output, QA.
- Create `scripts/download_noaa_ais.py`: thin download CLI.
- Create `scripts/inspect_noaa_ais.py`: thin schema-inspection CLI.
- Create `scripts/prepare_smoke_dataset.py`: thin preparation CLI.
- Modify `requirements.txt`: exact successfully installed runtime/test dependency versions.
- Modify `README.md`: reproducible local setup and explicit Phase 1 commands.
- Create `tests/unit/test_noaa_ais.py`: adapter unit tests.
- Create `tests/unit/test_preprocess.py`: transformation unit tests.
- Create `tests/integration/test_smoke_pipeline.py`: synthetic end-to-end integration test.
- Create `tests/fixtures/ais_points.parquet` only if an on-disk fixture is necessary and remains tiny; prefer generating it in pytest temporary directories.
- Create `data/manifests/noaa_ais_2024-01-01_sf_bay.json`: measured real-data manifest.
- Create `docs/data-provenance.md`: provenance and limitations.
- Create `docs/data-foundation-report.md`: measured QA report.

## Review Focus

- Existing final or partial download files: refusal, explicit overwrite, and cleanup must leave no misleading final file.
- Ambiguous GeoParquet metadata or non-EPSG:4326 geometry: inspect explicitly and transform only with a verified CRS; otherwise stop clearly.
- Null, non-finite, and boundary coordinates: reject invalid values while treating bbox edges as inclusive.
- Duplicate timestamp versus exact duplicate: remove only exact duplicate observations and separately count same-vessel timestamp collisions.
- A vessel history larger than 50,000 rows: never truncate it; skip it deterministically and report the exclusion.

---

### Task 1: Establish the local Python environment and dependency baseline

**Files:**
- Modify: `requirements.txt`
- Modify: `README.md`

**Interfaces:**
- Consumes: `C:\wu\python.exe` (Python 3.12.7).
- Produces: `.venv\Scripts\python.exe` and a reproducible, exact dependency list for all later tasks.

- [ ] **Step 1: Reconfirm repository and interpreter state**

Run:

```powershell
git status --short
git branch --show-current
git log -1 --oneline
git remote -v
& 'C:\wu\python.exe' --version
```

Expected: clean or documentation-only review changes, branch `feat/data-gis-foundation`, starting history containing `8b8b464`, no remotes, and Python 3.12.7.

- [ ] **Step 2: Create the local environment without changing global Python**

Run:

```powershell
& 'C:\wu\python.exe' -m venv .venv
& '.\.venv\Scripts\python.exe' --version
```

Expected: Python 3.12.7 from the project-local interpreter.

- [ ] **Step 3: Install only the approved dependencies**

Run the `.venv` interpreter's pip to install `pandas`, `numpy`, `pyarrow`, `shapely`, `pyproj`, and `pytest`. Do not install GeoPandas, DuckDB, scikit-learn, web frameworks, or frontend packages.

- [ ] **Step 4: Verify imports and capture exact versions**

Run one `.venv` Python command that imports all six packages and prints their versions. Record those exact versions in `requirements.txt`; do not use the global interpreter's package list.

- [ ] **Step 5: Document setup and verify ignore behavior**

Add concise PowerShell setup commands to `README.md`. Run `git status --short --ignored` and verify `.venv/` is ignored.

### Task 2: Implement safe official-source acquisition with TDD

**Files:**
- Create: `apps/api/seawatch/__init__.py`
- Create: `apps/api/seawatch/adapters/__init__.py`
- Create: `apps/api/seawatch/adapters/noaa_ais.py`
- Create: `scripts/download_noaa_ais.py`
- Create: `tests/unit/test_noaa_ais.py`

**Interfaces:**
- Consumes: HTTPS/file-like response data and a destination `pathlib.Path`.
- Produces: `DownloadRecord(source_url: str, destination: Path, content_length: int, sha256: str, download_utc: datetime)`; `sha256_file(path: Path) -> str`; `download_file(source_url: str, destination: Path, *, overwrite: bool = False, chunk_size: int = 1_048_576) -> DownloadRecord`.

- [ ] **Step 1: Write failing hashing and successful-download tests**

Add tests that serve known bytes from a local HTTP test server, assert the exact SHA-256 and size, assert a timezone-aware UTC completion time, and assert that the final destination contains exactly the source bytes.

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/unit/test_noaa_ais.py -k 'hash or successful_download' -v
```

Expected: failure because the adapter interfaces do not yet exist.

- [ ] **Step 3: Implement the minimum hashing and streamed-download behavior**

Implement `DownloadRecord`, `sha256_file`, and `download_file` with standard-library HTTP, streaming to a sibling `.partial` path and atomically renaming only after EOF and hash calculation.

- [ ] **Step 4: Run the focused tests and verify GREEN**

Run the command from Step 2. Expected: all selected tests pass.

- [ ] **Step 5: Write failing safety tests**

Add tests asserting: an existing destination raises without overwrite; `overwrite=True` replaces it; an HTTP error includes status/source context; a broken transfer does not create/replace the final file; and a stale `.partial` path is handled explicitly rather than mistaken for success.

- [ ] **Step 6: Run safety tests and verify RED**

Run `pytest tests/unit/test_noaa_ais.py -k 'existing or overwrite or http or partial' -v`. Expected: failures for the unimplemented safety behavior.

- [ ] **Step 7: Implement the minimum safety behavior and thin CLI**

The CLI defaults to the approved official URL and `data/raw/ais-2024-01-01.parquet`, exposes `--force`, prints destination/bytes/SHA-256/UTC time, and exits nonzero with a concise error. It delegates all data work to `download_file`.

- [ ] **Step 8: Run adapter tests and the full suite**

Run:

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/unit/test_noaa_ais.py -v
& '.\.venv\Scripts\python.exe' -m pytest
```

Expected: zero failures.

### Task 3: Inspect actual Parquet and GeoParquet metadata with TDD

**Files:**
- Modify: `apps/api/seawatch/adapters/noaa_ais.py`
- Create: `scripts/inspect_noaa_ais.py`
- Modify: `tests/unit/test_noaa_ais.py`

**Interfaces:**
- Consumes: local Parquet `Path`.
- Produces: `inspect_parquet(path: Path) -> ParquetInspection`, where the serializable record exposes columns/types/nullability, metadata row count, row groups, timestamp representation, Parquet key/value metadata, and decoded GeoParquet geometry/CRS facts.

- [ ] **Step 1: Write a failing local-metadata test**

Build a tiny GeoParquet-like file in `tmp_path` with known Arrow fields, row count, timestamp type, WKB point geometry, and `geo` metadata. Assert every public inspection field, including observable nullability and CRS.

- [ ] **Step 2: Run the inspection test and verify RED**

Run `pytest tests/unit/test_noaa_ais.py -k inspect_parquet -v`. Expected: failure because `ParquetInspection`/`inspect_parquet` is missing.

- [ ] **Step 3: Implement metadata inspection without reading the full dataset**

Use `pyarrow.parquet.ParquetFile` metadata/schema and decode the `geo` metadata as JSON. Preserve unknown metadata as `null` or an explicit observation, never as an assumption.

- [ ] **Step 4: Run the test and verify GREEN**

Run the command from Step 2. Expected: pass.

- [ ] **Step 5: Write failing malformed/ambiguous metadata tests**

Test a normal non-GeoParquet file, malformed `geo` JSON, missing primary geometry information, and an unreadable file. Pin clear exception types/messages for conditions that prevent safe processing while still allowing general Parquet schema reporting where possible.

- [ ] **Step 6: Implement error reporting and inspection CLI**

The CLI accepts a local Parquet path and writes or prints stable JSON. It must not infer geometry or CRS not present in the source.

- [ ] **Step 7: Verify adapter tests and full suite**

Run the adapter test file and then bare `pytest`. Expected: zero failures.

### Task 4: Implement canonical validation and filtering with TDD

**Files:**
- Create: `apps/api/seawatch/trajectories/__init__.py`
- Create: `apps/api/seawatch/trajectories/preprocess.py`
- Create: `tests/unit/test_preprocess.py`

**Interfaces:**
- Consumes: Arrow/Pandas observations plus an explicit inspected source-column mapping.
- Produces: `BoundingBox(west: float, south: float, east: float, north: float)`; `parse_utc_timestamps(values: Series) -> Series`; `valid_coordinate_mask(longitude: Series, latitude: Series) -> Series`; `bbox_mask(longitude: Series, latitude: Series, bbox: BoundingBox) -> Series`; `cargo_vessel_mask(vessel_type: Series) -> Series`; `canonicalize_observations(frame: DataFrame, column_map: Mapping[str, str], *, source_crs: object | None) -> DataFrame`.

- [ ] **Step 1: Write failing timestamp tests**

Assert naive documented source timestamps become UTC, offset timestamps convert to UTC, invalid timestamps are counted/rejected according to the canonicalization contract, and ordering compares timezone-aware UTC values.

- [ ] **Step 2: Verify timestamp RED, implement minimally, and verify GREEN**

Run the focused timestamp tests before and after implementing `parse_utc_timestamps`.

- [ ] **Step 3: Write failing coordinate and bbox tests**

Assert rejection of null, NaN, infinity, longitude outside `[-180, 180]`, and latitude outside `[-90, 90]`; assert all four approved bbox edges are inclusive and just-outside values are excluded.

- [ ] **Step 4: Verify coordinate RED, implement masks, and verify GREEN**

Run `pytest tests/unit/test_preprocess.py -k 'coordinate or bbox' -v` before and after implementing the masks.

- [ ] **Step 5: Write failing vessel-type and geometry canonicalization tests**

Assert numeric codes 70 through 79 are included, adjacent codes and nulls are excluded, verified WKB points become longitude/latitude, absent optional measurements remain absent, missing required fields fail clearly, and non-EPSG:4326 input is transformed before bbox use.

- [ ] **Step 6: Verify RED, implement canonicalization, and verify GREEN**

Use Shapely only for verified point decoding and PyProj only when the inspected CRS requires a transform. Reject ambiguous/unsupported CRS rather than treating degrees as metres.

- [ ] **Step 7: Run the full suite**

Run bare `pytest`. Expected: zero failures.

### Task 5: Implement ordering, deduplication, QA gaps, IDs, and complete-track selection with TDD

**Files:**
- Modify: `apps/api/seawatch/trajectories/preprocess.py`
- Modify: `tests/unit/test_preprocess.py`

**Interfaces:**
- Consumes: canonical observations containing local `source_vessel_id`, UTC timestamp, coordinates, and source measurements.
- Produces: `surrogate_track_id(source_vessel_id: object, source_date: date) -> str`; `order_and_deduplicate(frame: DataFrame) -> tuple[DataFrame, DuplicateStats]`; `summarize_time_gaps(frame: DataFrame) -> TimeGapStats`; `select_complete_tracks(frame: DataFrame, *, max_observations: int = 50_000) -> tuple[DataFrame, SelectionStats]`.

- [ ] **Step 1: Write failing surrogate-ID tests**

Assert exact stability for the same normalized source ID/date, difference across IDs, the documented 16-character lowercase hexadecimal form, and no raw identifier substring in representative output.

- [ ] **Step 2: Verify ID RED, implement the specified digest, and verify GREEN**

Implement exactly `SHA-256("seawatch:noaa-ais:2024-01-01:" + normalized_source_identifier)[:16 hex characters]`, parameterized by source date.

- [ ] **Step 3: Write failing ordering and duplicate tests**

Assert stable chronological vessel ordering, exact duplicate removal, retention/counting of non-identical observations sharing a timestamp, and no removal of unusual SOG/COG/heading values.

- [ ] **Step 4: Verify RED, implement ordering/deduplication, and verify GREEN**

Use a stable source-row ordinal only as a tie-breaker. Keep that field private unless output reproducibility requires it and the manifest records it as synthetic.

- [ ] **Step 5: Write failing time-gap tests**

Assert gaps are computed only within each vessel, report zero/negative anomalies separately if present, summarize positive gaps including counts above the project parameter of 10 minutes, and never insert interpolated observations.

- [ ] **Step 6: Verify RED, implement gap summaries, and verify GREEN**

Treat 10 minutes as a named project QA parameter, not a maritime standard and not a segmentation/anomaly rule.

- [ ] **Step 7: Write failing complete-track selection tests**

Cover: all rows retained below 50,000; deterministic ascending `track_id` selection above the maximum; no selected `track_id` is partial; input vessel order does not change selection; and a single track above the maximum is skipped/reported rather than truncated.

- [ ] **Step 8: Verify RED, implement selection, and verify GREEN**

Do not use point sampling, random sampling, temporal downsampling, or head/tail truncation.

- [ ] **Step 9: Run the full suite**

Run bare `pytest`. Expected: zero failures.

### Task 6: Implement output, manifest, and synthetic integration flow with TDD

**Files:**
- Modify: `apps/api/seawatch/trajectories/preprocess.py`
- Create: `scripts/prepare_smoke_dataset.py`
- Create: `tests/integration/test_smoke_pipeline.py`

**Interfaces:**
- Consumes: inspected source facts, verified download record, canonical eligible observations, output paths, approved bbox/source date, and processing version.
- Produces: `prepare_smoke_dataset(...) -> ProcessingResult`; `write_processed_parquet(frame: DataFrame, path: Path, *, overwrite: bool = False) -> ArtifactRecord`; `write_geojson_preview(frame: DataFrame, path: Path, *, max_tracks: int, overwrite: bool = False) -> ArtifactRecord`; `build_manifest(...) -> dict[str, object]`; `render_qa_report(...) -> str`.

- [ ] **Step 1: Write a failing synthetic end-to-end integration test**

Construct a tiny local source fixture containing valid/invalid coordinates, inside/outside bbox rows, cargo/non-cargo codes, out-of-order rows, an exact duplicate, a same-time non-identical observation, multiple vessels, missing measurements, and a time gap over 10 minutes.

Assert the processed result has only valid in-bbox cargo observations, exact duplicates removed, complete chronologically ordered histories, stable `track_id`, correct counts, and no raw source vessel identifier in public columns.

- [ ] **Step 2: Run integration test and verify RED**

Run `pytest tests/integration/test_smoke_pipeline.py -v`. Expected: failure because the orchestration/output interfaces are missing.

- [ ] **Step 3: Implement minimal orchestration and Parquet output**

Write canonical UTC timestamp and EPSG:4326 coordinates with output metadata. Refuse overwrite unless explicit. Ensure public output columns match the manifest contract and exclude the raw vessel identifier.

- [ ] **Step 4: Extend the failing integration test for GeoJSON privacy and complete tracks**

Assert the preview has only deterministic complete selected tracks, valid Point/LineString geometry, no key/value containing raw MMSI/source identifier, and an explicit small track cap.

- [ ] **Step 5: Implement GeoJSON preview and verify GREEN**

Use only standard JSON plus verified coordinate values; do not add GeoPandas. Add a defensive forbidden-column check before serialization.

- [ ] **Step 6: Extend the failing integration test for manifest and QA values**

Assert every required manifest key exists, actual values match the synthetic run, unknown values are JSON `null`, synthetic fields are labeled, no raw identifier values appear, and QA missing/duplicate/gap statistics match the fixture exactly.

- [ ] **Step 7: Implement manifest/report builders and thin preparation CLI**

CLI defaults: source date `2024-01-01`, bbox `[-122.55, 37.68, -122.25, 37.90]`, cargo codes 70-79, maximum 50,000, and gap QA threshold 10 minutes. All path overwrites require explicit permission.

- [ ] **Step 8: Run integration and full suites**

Run:

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/integration/test_smoke_pipeline.py -v
& '.\.venv\Scripts\python.exe' -m pytest
```

Expected: zero failures and no warnings left unexplained.

### Task 7: Verify official documentation, acquire the real source, and inspect it

**Files:**
- Create: `docs/data-provenance.md`
- Modify: `README.md`
- Create locally only: `data/raw/ais-2024-01-01.parquet`

**Interfaces:**
- Consumes: approved official source URL and official README URL.
- Produces: locally verified source bytes, `DownloadRecord`, `ParquetInspection`, and cited provenance facts for downstream processing.

- [ ] **Step 1: Verify official metadata and license**

Read the official NOAA/MarineCadastre documentation and its linked license source. Record only directly supported publisher, scope, license, and limitation facts in `docs/data-provenance.md`; if the claimed CC0 1.0 status is not supported, record the actual observed statement instead.

- [ ] **Step 2: Run the deterministic download CLI**

Run:

```powershell
& '.\.venv\Scripts\python.exe' scripts/download_noaa_ais.py
```

Expected: successful official HTTP acquisition, printed destination, measured byte size, UTC timestamp, and SHA-256. If it fails, stop this task and report the failure without substitution.

- [ ] **Step 3: Independently verify the downloaded file**

Run a second SHA-256 calculation and filesystem byte-size check, compare them with the CLI record, and check that no `.partial` file remains.

- [ ] **Step 4: Inspect the actual Parquet/GeoParquet schema**

Run the inspection CLI. Review every source column/type, metadata row count, row groups, nullability, timestamps, geometry encoding/types, and CRS. Create the explicit semantic column mapping only from these results.

- [ ] **Step 5: Verify Git exclusion immediately**

Run `git status --short --ignored data/raw`. Expected: the real source is ignored and not staged.

### Task 8: Produce real smoke artifacts and measured documentation

**Files:**
- Create locally only: `data/processed/<measured-output>.parquet`
- Create locally only: `data/processed/<measured-preview>.geojson`
- Create: `data/manifests/noaa_ais_2024-01-01_sf_bay.json`
- Create: `docs/data-provenance.md`
- Create: `docs/data-foundation-report.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: `DownloadRecord`, `ParquetInspection`, actual semantic mapping, and real local source.
- Produces: measured local artifacts plus committed manifest/report/provenance documentation.

- [ ] **Step 1: Run the explicit real-data preparation command**

Pass the resolved actual column mapping when it differs from canonical defaults. Use the approved bbox, cargo codes 70-79, maximum 50,000, and no temporal downsampling.

- [ ] **Step 2: Validate selection sufficiency without changing scope silently**

If bbox records exist but cargo records do not, report that measured result and stop for review rather than substituting vessel types. If eligible cargo rows exceed 50,000, verify every selected vessel history is complete and every skipped reason is recorded.

- [ ] **Step 3: Validate local processed Parquet**

Re-open it and assert row count, canonical schema, UTC timestamp range, chronological order within every `track_id`, coordinate validity/bbox inclusion, cargo codes, uniqueness after exact deduplication, and absence of raw source identifier columns.

- [ ] **Step 4: Validate local GeoJSON preview**

Parse the JSON, inspect all properties and serialized text for raw source identifier names/values, confirm the deterministic track cap, and verify each included feature represents a complete selected history.

- [ ] **Step 5: Write the measured manifest**

Populate exactly: `dataset_id`, `publisher`, `source_url`, `source_readme_url`, `observed_license`, `license_url`, `download_utc`, `source_date`, `content_length`, `sha256`, `geographic_bbox`, `vessel_type_filter`, `source_columns`, `output_columns`, `crs`, `timezone`, `source_rows`, `bbox_rows`, `filtered_rows`, `output_rows`, `surrogate_id_method`, `processing_version`, `git_commit_or_version_reference`, `synthetic_fields`, and `notes`. Use `null` plus a note for anything not observed.

- [ ] **Step 6: Write provenance and measured QA documentation**

Include all requested limitations and measured statistics. The report must state source bytes/rows, bbox/cargo/output rows, vessels/tracks, timestamp range, requested missing rates, coordinate validity, duplicates, time-gap summary, and artifact sizes. Do not copy estimates from the brief.

- [ ] **Step 7: Verify generated artifact ignore behavior**

Run `git status --short --ignored data/raw data/processed`. Expected: real raw and processed artifacts are ignored; only intended manifest/docs are visible as changes.

### Task 9: Final verification, staging audit, and single local commit

**Files:**
- Review all changed files.
- Do not create any additional feature files during this task except corrections driven by verification failures.

**Interfaces:**
- Consumes: all implementation, tests, measured documentation, and local artifacts.
- Produces: one verified local commit and the exact Phase 1 final report requested by the project brief.

- [ ] **Step 1: Run fresh full verification**

Run:

```powershell
& '.\.venv\Scripts\python.exe' -m pytest
git diff --check
```

Expected: zero test failures and no `git diff --check` output.

- [ ] **Step 2: Re-run explicit real-artifact validation**

Run the inspection/preparation validation command against the already downloaded local NOAA file without overwriting outputs. Confirm recorded source hash and every report/manifest count still match local artifacts.

- [ ] **Step 3: Audit scope and secrets before staging**

Use `git status --short --ignored`, `git diff --stat`, `git diff`, and repository searches for `.env`, credentials, raw source names, raw MMSI fields/values in preview/public artifacts, `.venv`, `node_modules`, model libraries, API/frontend files, and challenge #10 work. Resolve every unexpected result.

- [ ] **Step 4: Stage only explicit approved paths**

Stage code, tests, requirements, README, design/plan, manifest, provenance, and report individually. Do not use a broad command that could accidentally include ignored or unrelated files.

- [ ] **Step 5: Inspect the exact staged file list and staged diff**

Run:

```powershell
git diff --cached --name-status
git diff --cached --check
git diff --cached
```

Expected: no raw/processed real artifacts, `.env`, credentials, `.venv`, `node_modules`, ML/frontend/logistics work, or unrelated user changes.

- [ ] **Step 6: Run tests once more against the staged worktree state**

Run bare `.venv` pytest and require zero failures. If any correction is made, repeat Steps 1 through 6.

- [ ] **Step 7: Create the one authorized local commit**

Run:

```powershell
git commit -m "feat: establish NOAA AIS data foundation"
```

Do not push and do not add a remote.

- [ ] **Step 8: Capture final evidence**

Run:

```powershell
git log -1 --oneline
git status --short
git remote -v
```

Report exactly the 18 requested items: starting branch/SHA, working branch, interpreter, dependencies, source URL, measured source size/hash/schema, bbox and all row counts, vessel/track count, artifacts, test results, `git diff --check`, commit SHA, final short status, limitations/blockers, and recommended next phase. Stop without starting Phase 2.
