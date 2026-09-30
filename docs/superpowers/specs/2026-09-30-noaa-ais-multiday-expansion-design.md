# SeaWatch Phase 3A NOAA AIS Multi-Day Expansion Design

**Status:** Proposed for review; design and planning only

**Date:** 2026-09-30

**Base:** `feat/trajectory-features` at
`d0bdd977989a3ff74f9aa0ff9760685123f1f4a9`

## 1. Purpose and boundaries

Phase 3A expands the validated 2024-01-01 San Francisco Bay cargo-vessel
dataset with exactly two additional NOAA AIS daily artifacts: 2024-01-02 and
2024-01-03. Each date passes independently through the existing ingestion,
complete-track selection, segmentation, windowing, and trajectory-feature
pipeline. The output is a manifest-defined three-date corpus with fixed
train/calibration/test roles for later baseline evaluation.

This phase is data engineering and data-quality work. It does not implement,
fit, tune, score, or evaluate an anomaly detector. It does not change any
Phase 2 feature name, definition, unit, validity gate, segmentation rule, or
window rule. It does not add API, UI, logistics, persistence, cloud, hardware,
or deployment work.

Only these source dates are in scope:

| Date | Phase 3 role | Approved source | Acquisition action |
|---|---|---|---|
| 2024-01-01 | train/reference | `https://ocmgeodatastor1.blob.core.windows.net/marinecadastre/ais2024/ais-2024-01-01.parquet` | reuse the existing validated local artifacts |
| 2024-01-02 | calibration | `https://ocmgeodatastor1.blob.core.windows.net/marinecadastre/ais2024/ais-2024-01-02.parquet` | download and validate once during implementation |
| 2024-01-03 | test/holdout | `https://ocmgeodatastor1.blob.core.windows.net/marinecadastre/ais2024/ais-2024-01-03.parquet` | download and validate once during implementation |

No fallback, adjacent, replacement, or supplementary date may be downloaded.
If either approved artifact is unavailable or materially incompatible, the
workflow stops and reports the discrepancy.

## 2. Current authoritative baseline

The design starts from the two validated commits supplied by the user:

- Phase 1: `5823b14` (`feat: establish NOAA AIS data foundation`)
- Phase 2: `d0bdd97` (`feat: add deterministic trajectory feature pipeline`)

The current 2024-01-01 baseline contains 5,581 processed observations, 15
complete tracks, 15 segments, 3,216 candidate windows, 2,829 accepted windows,
and 387 windows rejected for insufficient observations. It is WGS84
(`EPSG:4326`) with UTC timestamps. All future per-date feature artifacts must
embed the same Phase 2 configuration hash:
`70aa8dd26c6f438c5122b48a497aad426fc5e4661829ff54611a266048f92a02`.

The unchanged Phase 2 settings are:

| Setting | Value |
|---|---:|
| segment gap | strictly greater than 600 seconds |
| window duration | 1,800 seconds |
| window stride | 300 seconds |
| minimum observations | 10 |
| minimum observed span | 1,200 seconds |
| minimum valid fraction | 0.80 |
| low-speed threshold | 3.0 knots |
| course speed gate | 1.0 knot |
| ratio displacement floor | 50 metres |

The 50,000-observation setting remains a per-date maximum ceiling, not a
target. Selection preserves complete chronological histories; it must not
truncate a track or randomly sample individual observations to approach the
ceiling.

## 3. Considered approaches

### Recommended: independent daily pipelines plus a manifest-defined cohort

Process every day separately, retain date-specific artifacts and provenance,
and create a committed cohort manifest that assigns each daily feature
artifact to one split. This preserves boundaries, makes discrepancies visible,
allows a single date to be regenerated, and avoids copying the same windows
into split-specific Parquet files.

### Rejected: concatenate observations before segmentation and windowing

Cross-date preprocessing could create accidental midnight continuity, obscure
source-specific schema or quality problems, and make it harder to reproduce a
single date. Even though current surrogate identifiers are date-scoped, the
pipeline must not depend on that detail to prevent cross-date windows.

### Rejected: duplicate physical Parquet files for train/calibration/test

Each split contains exactly one date, so copying daily window Parquets into
separate split folders adds storage, hash, and overwrite risks without adding
isolation. The cohort manifest is the split contract.

## 4. Data expansion design

Commit a strict source catalog at `config/noaa_ais_phase3a_dates.json`. It
contains exactly three entries, in chronological order, with date, approved
NOAA URL, expected raw filename, and split role. The URLs follow the verified
NOAA 2024 daily layout, but implementation must validate the downloaded
objects rather than treating the URL pattern as proof of schema or content.

The download CLI accepts a catalog date and refuses dates outside the three
entries. Phase 3A execution invokes it only for 2024-01-02 and 2024-01-03.
Normal tests mock transport and perform no network access.

Each new date follows this sequence independently:

1. Download the exact catalog URL atomically and record actual content length,
   SHA-256, retrieval UTC, and resolved destination.
2. Inspect the actual Parquet and GeoParquet metadata before preparation.
3. Verify publisher documentation, observed license, schema, WKB Point
   geometry, CRS, timestamp coverage, and source date.
4. Apply the existing SF Bay bounding box and cargo-type filter.
5. Select complete tracks deterministically under the 50,000-observation
   ceiling, preserving full chronological histories.
6. Write the existing eight-column public Phase 1 contract.
7. Run the unchanged Phase 2 segmentation, window, and feature pipeline with
   the exact committed configuration.
8. Produce per-date manifests and aggregate QA documents from measured values.

Processing stops before adapting if a new artifact materially differs in
license, CRS, geometry encoding/type, required source columns, timestamp/date
semantics, or geographic meaning. Small measured differences in row counts,
track counts, spacing, missingness, or movement distributions are expected and
must be reported rather than forced to match January 1.

## 5. Folder and artifact strategy

Generated raw, preview, processed, and feature Parquet/GeoJSON files remain
ignored and local. Code, configuration, tests, per-date manifests, the cohort
manifest, and aggregate measured reports are commit-eligible.

```text
config/
  noaa_ais_phase3a_dates.json                       # committed source/split catalog
  noaa_ais_2024_columns.json                        # existing unchanged mapping
  trajectory_features_v1.json                       # existing unchanged features

data/raw/                                           # ignored except .gitkeep
  ais-2024-01-02.parquet
  ais-2024-01-02.parquet.download.json
  ais-2024-01-02.inspection.json
  ais-2024-01-03.parquet
  ais-2024-01-03.parquet.download.json
  ais-2024-01-03.inspection.json

data/processed/                                     # ignored except .gitkeep
  noaa_ais_2024-01-02_sf_bay.parquet
  noaa_ais_2024-01-02_sf_bay_preview.geojson
  noaa_ais_2024-01-03_sf_bay.parquet
  noaa_ais_2024-01-03_sf_bay_preview.geojson
  features/
    noaa_ais_2024-01-02_sf_bay_segmented.parquet
    noaa_ais_2024-01-02_sf_bay_segments.parquet
    noaa_ais_2024-01-02_sf_bay_windows.parquet
    noaa_ais_2024-01-03_sf_bay_segmented.parquet
    noaa_ais_2024-01-03_sf_bay_segments.parquet
    noaa_ais_2024-01-03_sf_bay_windows.parquet

data/manifests/                                     # committed aggregate metadata
  noaa_ais_2024-01-02_sf_bay.json
  noaa_ais_2024-01-02_sf_bay_trajectory_features.json
  noaa_ais_2024-01-03_sf_bay.json
  noaa_ais_2024-01-03_sf_bay_trajectory_features.json
  noaa_ais_2024-01-01_to_2024-01-03_sf_bay_phase3a.json

docs/
  phase3a-data-expansion-report.md                   # committed cross-date QA
  qa/noaa-ais-2024-01-02-data-foundation.md          # committed measured daily QA
  qa/noaa-ais-2024-01-02-trajectory-features.md
  qa/noaa-ais-2024-01-03-data-foundation.md
  qa/noaa-ais-2024-01-03-trajectory-features.md
```

No combined three-day observation or window Parquet is produced. Consumers
resolve split members from the cohort manifest and read the referenced daily
artifact directly.

## 6. Manifest strategy

### Per-date manifests

January 2 and January 3 receive the same Phase 1 and Phase 2 manifest schemas
as January 1. Measured values override planning assumptions. Each manifest
records source and output hashes/sizes/counts, source date and URL, actual
schema/CRS/timezone/license evidence, selection statistics, configuration
path/hash/values, generator version, feature missingness, aggregate
distributions, and artifact paths.

The Phase 1 processing and Phase 2 generator version strings stay unchanged
when behavior is unchanged. Phase 3A is represented by the cohort schema, not
by relabeling the established algorithms.

### Cohort manifest

`noaa_ais_2024-01-01_to_2024-01-03_sf_bay_phase3a.json` is the authoritative
multi-day contract. Its schema version is `phase3a-multiday-v1` and it records:

- ordered dates and exact split assignment;
- paths and SHA-256 values for every daily Phase 1/2 manifest and feature
  artifact;
- the shared column-map and feature-configuration hashes;
- the shared bounding box, cargo filter, CRS, timezone, license, and pipeline
  versions;
- per-date and total observations, tracks, segments, candidate/accepted/
  rejected windows, and rejection reasons;
- zero-inclusive windows-per-track/segment summaries;
- per-feature missingness and required cross-date quantiles;
- comparability checks and any failed checks;
- the Phase 3B readiness decision and evidence;
- explicit notes that overlapping windows are dependent and that `track_id`
  is not anonymization.

The builder rejects missing/duplicate dates, unapproved dates, role changes,
hash mismatches, inconsistent configuration/column-map hashes, schema or CRS
differences, non-UTC data, date-range violations, and forbidden public
identifier fields. It never silently drops a daily member.

## 7. Date-based split strategy

The split is fixed before January 2 or January 3 is inspected:

```text
train/reference  = 2024-01-01
calibration      = 2024-01-02
test/holdout     = 2024-01-03
```

These roles are chronological, deterministic, and stored in the source
catalog and cohort manifest. They cannot be reassigned after seeing counts or
distributions. The current Phase 3A report may compare predeclared aggregate
QA metrics across all dates, including the test date, but future Phase 3B work
must not use January 3 movement values to choose features, preprocessing,
model hyperparameters, thresholds, or rules.

January 1 may support fitting a future baseline. January 2 may support
calibration or model selection. January 3 is reserved for a one-time final
evaluation after the Phase 3B experiment protocol is frozen. Any future
normalization, imputation, reference distribution, or learned transform must
be fitted on January 1 only and then applied unchanged to later dates.

## 8. Leakage prevention rules

1. Run ingestion, segmentation, windowing, and features independently by date.
2. Never create a segment or window spanning midnight or two daily artifacts.
3. Freeze and hash the Phase 1 column mapping, bounding box, cargo filter, and
   Phase 2 configuration before processing January 2 or January 3.
4. Do not revise feature definitions or sufficiency gates after observing new
   dates within this phase.
5. Assign splits from the committed catalog, never from measured behavior.
6. Do not pool dates before a consumer explicitly selects its allowed split.
7. Future fitted transforms use train/reference only; calibration can tune
   thresholds; test cannot influence either.
8. Cross-date QA uses only predeclared aggregate metrics. It does not publish
   row-level histories, direct source identifiers, or individual track IDs.
9. Track surrogates remain date-scoped. Phase 3A does not attempt cross-date
   vessel identity linkage, and it does not claim vessel-level independence.
10. Duplicate source bytes, timestamp leakage outside the named UTC date, or a
    daily artifact referenced by more than one split is a hard failure.

## 9. Cross-date QA metrics

The report presents each date independently, three-date totals where valid,
and absolute/percentage differences from January 1. Counts are not balanced
by truncation or sampling.

### Source and ingestion integrity

- raw content length and SHA-256;
- source rows and UTC timestamp minimum/maximum;
- required source schema and GeoParquet geometry metadata;
- publisher, observed license, CRS, and timezone;
- SF Bay bounding-box rows and cargo-filtered rows;
- invalid/missing time, coordinate, SOG, COG, and heading counts;
- exact duplicates removed and remaining zero-duration intervals;
- selected observation and complete-track counts;
- unselected complete tracks/observations due only to the maximum ceiling.

### Segmentation and window quality

- tracks and segments, segments per track, segment duration, and observations
  per segment;
- candidate, accepted, and rejected windows with every rejection reason;
- zero-inclusive windows per track and segment;
- observed span, median/max gap, and duplicate-time interval distributions;
- tracks and segments producing no full window;
- accepted-window concentration, including maximum single-track share;
- nominal overlap factor and an approximate non-overlapping-window count.

### Feature availability and descriptive movement QA

- missing count/rate for every Phase 2 feature;
- min, p25, median, p75, p95, and max for input SOG, max gap, path distance,
  displacement, path/displacement ratio, course-change features, and
  low-speed features;
- heading/COG relation availability;
- finite-value and valid-range checks;
- cross-date quantile and missingness deltas.

Distribution differences are descriptive QA, not anomaly labels. A shift is a
data-readiness concern only when it indicates collection, schema, processing,
coverage, or missingness incompatibility; genuine behavioral variation is not
silently normalized away.

## 10. Error handling and reproducibility

All writes use final-plus-`.partial` atomic behavior and preflight final,
partial, input, and output path aliases. Existing artifacts require explicit
`--force`. A failed date must not leave a cohort manifest claiming success.
The cohort manifest is written only after all three daily lineages validate.

Network activity is limited to two explicit smoke commands for January 2 and
January 3. Unit and integration tests remain offline. January 1 is never
automatically redownloaded. Rerunning preparation from verified local raw
artifacts must reproduce the measured rows, schemas, splits, and aggregate
manifest content; artifact hashes are verified in the same environment.

## 11. Tests required

Automated tests must cover:

- exact catalog dates, URLs, roles, and chronological order;
- rejection of any fourth date, URL/date mismatch, duplicate date, missing
  split, or changed role;
- mocked January 2/3 downloads and proof that tests perform no network access;
- source-date timestamp confinement and source-record/hash verification;
- date-scoped surrogate stability and differing surrogates across dates;
- complete-track ceiling behavior without point truncation or random sampling;
- independent per-date processing and absence of cross-date segments/windows;
- unchanged Phase 1 schema and unchanged Phase 2 feature/configuration contract;
- exact train/calibration/test membership;
- cohort aggregation, zero-window members, missing values, and totals;
- rejection of config, CRS, schema, timezone, hash, artifact, or split mismatch;
- fail-closed public identifier checks;
- output/partial/input path-collision protection;
- deterministic reruns and unchanged Phase 1/2 regression tests.

Real NOAA validation remains an explicit smoke workflow after automated tests.

## 12. Expected implementation sequence

1. Add and validate the strict three-date source/split catalog.
2. Parameterize the existing NOAA download and preparation CLIs by approved
   catalog date while retaining January 1 defaults and compatibility.
3. Add offline cohort-manifest and cross-date QA builders.
4. Add a cohort CLI that consumes completed daily manifests/artifacts but never
   downloads data.
5. Complete all synthetic tests and the full Phase 1/2 regression suite.
6. Explicitly download January 2 only, inspect it, and stop on material source
   discrepancy.
7. Explicitly download January 3 only, inspect it, and stop on material source
   discrepancy.
8. Prepare daily Phase 1 and Phase 2 artifacts with unchanged configuration.
9. Build and independently audit the cohort manifest and report.
10. Audit Git status, staged names/sizes, privacy, secrets, ignored generated
    artifacts, and exact commit scope before any implementation commit.

## 13. Phase 3B readiness criteria

Phase 3B may begin with baseline anomaly experiments only if all of the
following are measured and pass:

- all three approved dates have verified source, schema, license, CRS, UTC,
  timestamp confinement, and complete provenance;
- daily processed and feature artifacts reproduce and match their manifests;
- the column-map and Phase 2 configuration hashes are identical across dates;
- no segment/window crosses a date and every split has exactly one date;
- each date has at least 10 tracks producing accepted windows, at least 100
  approximate non-overlapping windows, and no single track contributes more
  than 20% of accepted windows;
- core SOG/path/displacement feature missingness is at most 20% per date;
- every feature intended for a future experiment has declared, measured
  support on train and calibration data; unsupported angular/ratio features
  are not silently zero-filled;
- no unexplained schema, collection, timestamp, or missingness discontinuity
  makes one date incomparable;
- the future experiment protocol fixes training transforms, calibration use,
  and one-time test evaluation before reading test outcomes;
- the report explicitly accounts for window overlap and same-vessel dependence
  rather than treating raw window count as independent sample size.

Failure of any hard integrity criterion yields Gate B. A sample-size or
feature-coverage failure also yields B unless a narrower, explicitly reviewed
baseline question can be supported without changing Phase 2 definitions.

## 14. Current gate decision

**B. NEED ADDITIONAL DATA INVESTIGATION**

Only January 1 is currently measured and validated. January 2 and January 3
have not yet been downloaded or inspected, so their compatibility, track
coverage, effective sample size, missingness, and split suitability are
unknown. Phase 3A implementation should acquire exactly those two dates and
re-run the criteria above. This design does not authorize Phase 3B modeling or
any additional date acquisition.
