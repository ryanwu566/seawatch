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

### Application Layer *(planned)*

- FastAPI
- React + TypeScript
- MapLibre

### Optimization *(planned)*

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

## Development Status

### Completed

- ✅ NOAA AIS data foundation
- ✅ GeoParquet ingestion pipeline
- ✅ Trajectory segmentation
- ✅ Geodesic movement features
- ✅ Multi-day AIS cohort preparation
- ✅ Explainable anomaly ranking baseline
- ✅ Statistical baseline comparison

### Current

- 🚧 Human review workflow

### Future

- ⏳ Maritime investigation dashboard
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
│   ├── api/
│   └── web/
├── data/
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
