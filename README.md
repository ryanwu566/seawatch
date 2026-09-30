# SeaWatch

## Explainable Maritime Intelligence & Resilience Decision Support

**TDTH 2026 — Maritime Track Anomaly & Grey-Zone Behavior Alerting**

---

## Overview

SeaWatch is an AI-assisted geospatial decision-support system that analyzes maritime vessel trajectories and identifies behavior patterns requiring human review.

By combining AIS data processing, trajectory analytics, and explainable ranking methods, SeaWatch helps analysts understand:

- What changed?
- Why is this trajectory different?
- Which behaviors require further investigation?

The system is designed as a **human-in-the-loop decision-support platform**, not an automated intent classifier.

---

## Problem

Modern maritime environments generate large-scale vessel movement data.

The challenge is not only detecting unusual patterns, but also:

- reducing unnecessary alerts
- explaining behavioral differences
- understanding uncertainty
- supporting human decision-making

SeaWatch focuses on **explainable behavioral intelligence rather than black-box prediction**.

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

Planned:

- FastAPI backend
- React + TypeScript frontend
- MapLibre geospatial visualization

### Optimization Layer

Planned:

- NetworkX-based logistics simulation

---

## Data

Current prototype uses:

- NOAA MarineCadastre AIS GeoParquet
- Historical AIS observations
- WGS84 geospatial processing

SeaWatch treats AIS data as behavioral observations.

The system does not automatically determine intent or classify vessels.

---

## Development Progress

### Completed

✅ NOAA AIS data foundation  
✅ GeoParquet ingestion pipeline  
✅ Trajectory segmentation  
✅ Geodesic movement features  
✅ Multi-day AIS cohort preparation  

### Current Development

🚧 Explainable anomaly ranking  
🚧 Statistical baseline comparison  
🚧 Human review workflow  

### Future

⏳ Maritime investigation dashboard  
⏳ Emergency logistics simulation  
⏳ Edge deployment exploration  

---

## Project Roadmap

### Phase 1 — Data Foundation ✅

Completed:

- Official AIS data acquisition
- Data validation
- Provenance tracking
- Reproducible preprocessing

### Phase 2 — Trajectory Intelligence ✅

Completed:

- Track segmentation
- Time-window generation
- Movement feature engineering

### Phase 3 — Explainable Ranking 🚧

Current:

- Behavior deviation ranking
- Statistical baseline evaluation
- Explainable alert generation

### Phase 4 — Decision Dashboard ⏳

Planned:

- Interactive maritime map
- Track investigation interface
- Human feedback workflow

### Phase 5 — Resilience Extension ⏳

Planned:

- Emergency logistics simulation
- Disruption scenario analysis

---

## Research Principles

SeaWatch follows:

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