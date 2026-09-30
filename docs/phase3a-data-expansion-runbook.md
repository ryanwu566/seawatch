# Phase 3A NOAA AIS Multi-Day Expansion Runbook

Phase 3A adds only 2024-01-02 and 2024-01-03 to the already validated
2024-01-01 lineage. Every date is prepared, segmented, windowed, and featured
independently. The workflow creates an aggregate cohort manifest, not a merged
observation or feature dataset. It performs no anomaly scoring.

Use the existing project environment created from `C:\wu\python.exe` (Python
3.12.7). Do not install into or replace global Python.

## Safety and discrepancy stops

Before processing each download, inspect the actual local Parquet and compare
its measured source date, source schema, GeoParquet WKB Point geometry, CRS,
publisher documentation, and observed CC0 license with the January 1 contract.
Stop before adapting code or downloading the next date if any of those differs
materially. Row counts and movement distributions may differ and must be
reported as measured.

The commands below never select January 1 or a fourth date for download.
Automated tests do not invoke these commands and do not use the network.

## 1. Download and inspect January 2

```powershell
& '.\.venv\Scripts\python.exe' scripts/download_noaa_ais.py --date 2024-01-02
& '.\.venv\Scripts\python.exe' scripts/inspect_noaa_ais.py `
  data/raw/ais-2024-01-02.parquet `
  --output data/raw/ais-2024-01-02.inspection.json
```

Review the inspection before continuing. Then create the date-isolated Phase 1
artifacts and aggregate documentation:

```powershell
& '.\.venv\Scripts\python.exe' scripts/prepare_smoke_dataset.py `
  --source-date 2024-01-02 `
  --publisher 'NOAA Office for Coastal Management' `
  --observed-license 'CC0 1.0 Universal' `
  --license-url 'https://github.com/ocm-marinecadastre/ais-vessel-traffic/blob/main/LICENSE.md'
```

Run the unchanged Phase 2 configuration with explicit date-specific paths:

```powershell
& '.\.venv\Scripts\python.exe' scripts/prepare_trajectory_features.py `
  --source data/processed/noaa_ais_2024-01-02_sf_bay.parquet `
  --source-manifest data/manifests/noaa_ais_2024-01-02_sf_bay.json `
  --config config/trajectory_features_v1.json `
  --segmented-output data/processed/features/noaa_ais_2024-01-02_sf_bay_segmented.parquet `
  --segments-output data/processed/features/noaa_ais_2024-01-02_sf_bay_segments.parquet `
  --windows-output data/processed/features/noaa_ais_2024-01-02_sf_bay_windows.parquet `
  --manifest-output data/manifests/noaa_ais_2024-01-02_sf_bay_trajectory_features.json `
  --report-output docs/qa/noaa-ais-2024-01-02-trajectory-features.md
```

## 2. Download and inspect January 3

Only after January 2 passes its source and lineage checks:

```powershell
& '.\.venv\Scripts\python.exe' scripts/download_noaa_ais.py --date 2024-01-03
& '.\.venv\Scripts\python.exe' scripts/inspect_noaa_ais.py `
  data/raw/ais-2024-01-03.parquet `
  --output data/raw/ais-2024-01-03.inspection.json
```

Review the inspection, then run the independent January 3 pipelines:

```powershell
& '.\.venv\Scripts\python.exe' scripts/prepare_smoke_dataset.py `
  --source-date 2024-01-03 `
  --publisher 'NOAA Office for Coastal Management' `
  --observed-license 'CC0 1.0 Universal' `
  --license-url 'https://github.com/ocm-marinecadastre/ais-vessel-traffic/blob/main/LICENSE.md'

& '.\.venv\Scripts\python.exe' scripts/prepare_trajectory_features.py `
  --source data/processed/noaa_ais_2024-01-03_sf_bay.parquet `
  --source-manifest data/manifests/noaa_ais_2024-01-03_sf_bay.json `
  --config config/trajectory_features_v1.json `
  --segmented-output data/processed/features/noaa_ais_2024-01-03_sf_bay_segmented.parquet `
  --segments-output data/processed/features/noaa_ais_2024-01-03_sf_bay_segments.parquet `
  --windows-output data/processed/features/noaa_ais_2024-01-03_sf_bay_windows.parquet `
  --manifest-output data/manifests/noaa_ais_2024-01-03_sf_bay_trajectory_features.json `
  --report-output docs/qa/noaa-ais-2024-01-03-trajectory-features.md
```

The 50,000-observation setting is a per-date ceiling. The preparation command
selects complete chronological track histories and never truncates or randomly
samples observations to approach it.

## 3. Build the offline cohort

After all three daily lineages exist and validate:

```powershell
& '.\.venv\Scripts\python.exe' scripts/build_phase3a_cohort.py
```

The fixed manifest roles are:

- 2024-01-01: train/reference
- 2024-01-02: calibration
- 2024-01-03: held-out test

The builder verifies daily hashes, artifact sizes and rows, public schemas,
CRS/timezone metadata, date confinement, configuration identity, role identity,
and forbidden identifier absence before atomically publishing the cohort
manifest and report.

## 4. Verification and privacy audit

```powershell
& '.\.venv\Scripts\python.exe' -m pytest -q
& '.\.venv\Scripts\python.exe' -m compileall -q apps scripts
git check-ignore data/raw/ais-2024-01-02.parquet `
  data/raw/ais-2024-01-03.parquet `
  data/processed/noaa_ais_2024-01-02_sf_bay.parquet `
  data/processed/noaa_ais_2024-01-03_sf_bay.parquet `
  data/processed/features/noaa_ais_2024-01-02_sf_bay_windows.parquet `
  data/processed/features/noaa_ais_2024-01-03_sf_bay_windows.parquet
rg -n -i 'mmsi|source_vessel_id|vessel_name|call_sign' `
  data/manifests/noaa_ais_2024-01-01_to_2024-01-03_sf_bay_phase3a.json `
  docs/phase3a-data-expansion-report.md
```

Generated raw, processed Parquet, GeoJSON, inspection, and download-sidecar
artifacts remain local and ignored. Commit only code, tests, configuration,
manifests, measured reports, and provenance documentation. The cohort report
must choose readiness Gate A or Gate B from measured criteria and then stop;
it does not authorize Phase 3B modeling or acquisition of another date.
