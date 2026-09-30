# SeaWatch

SeaWatch is a geospatial decision-support prototype for TDTH 2026.

## Core Direction

Challenge #07 — Maritime Track Anomaly & Grey-Zone Behavior Alerting

Planned capabilities:

- Historical vessel-track replay
- Interpretable trajectory anomaly detection
- Behavioral reason codes
- Data-quality and uncertainty indicators
- Alert-threshold comparison
- Human false-positive review

## Optional Extension

Challenge #10 — Emergency Logistics Under Network & Transport Disruption

The logistics module is designed to remain independent from the core #07 system.

## Architecture

- Frontend: React + TypeScript + MapLibre
- Backend: FastAPI
- Data: Parquet + SQLite
- Analysis: Python + scikit-learn
- Optional optimization: NetworkX

## Project Status

Initial project structure established.

## Phase 1 Data Foundation Setup

Create the project-local environment with the approved Python 3.12.7
interpreter. These commands do not modify the global Python installation:

```powershell
& 'C:\wu\python.exe' -m venv .venv
& '.\.venv\Scripts\python.exe' -m pip install -r requirements.txt
& '.\.venv\Scripts\python.exe' -m pytest
```

The NOAA AIS download and smoke-dataset commands are documented with the
Phase 1 implementation. Real raw and processed data remain local and are
ignored by Git.

Download and inspect only the approved 2024-01-01 source:

```powershell
& '.\.venv\Scripts\python.exe' scripts/download_noaa_ais.py
& '.\.venv\Scripts\python.exe' scripts/inspect_noaa_ais.py `
  data/raw/ais-2024-01-01.parquet
```

Preparation requires an explicit JSON mapping from the inspected source
columns to the canonical fields. The verified mapping is committed at
`config/noaa_ais_2024_columns.json`. Run the explicit real-data smoke workflow
with:

```powershell
& '.\.venv\Scripts\python.exe' scripts/prepare_smoke_dataset.py `
  --publisher 'NOAA Office for Coastal Management' `
  --observed-license 'CC0 1.0 Universal' `
  --license-url 'https://github.com/ocm-marinecadastre/ais-vessel-traffic/blob/main/LICENSE.md' `
  --force
```

`--force` explicitly regenerates the committed measured manifest and QA report
as well as the ignored local data artifacts. Without it, the command preflights
all destinations and exits before processing if any output already exists.

The smoke workflow is not part of the automated test suite. See
`docs/data-provenance.md` and `docs/data-foundation-report.md` for the source
and measured results.

## Phase 2 Trajectory Features

Phase 2 deterministically segments and windows the existing local Phase 1
Parquet and computes neutral movement features. It does not download data or
perform anomaly detection. The real-data workflow is explicit and remains
outside normal tests:

```powershell
& '.\.venv\Scripts\python.exe' scripts/prepare_trajectory_features.py --force
```

Generated segmented, summary, and feature Parquet files remain ignored and
local. Only aggregate provenance and QA documentation are committed. See
`docs/trajectory-feature-spec.md` for the exact feature and quality contract.
