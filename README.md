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
