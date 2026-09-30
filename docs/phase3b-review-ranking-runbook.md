# Phase 3B Offline Review-Ranking Runbook

Phase 3B ranks behavioral deviations for human review. It does not assign event labels, infer intent, or establish legality or danger. `review_priority_score` is a deterministic ranking value, not a probability or confidence measure.

## Environment

Use only the project-local environment created from `C:\wu\python.exe`:

```powershell
& '.\.venv\Scripts\python.exe' --version
& '.\.venv\Scripts\python.exe' -m pip install -r requirements.txt
& '.\.venv\Scripts\python.exe' -c "import sklearn; print(sklearn.__version__)"
```

Expected versions are Python 3.12.7 and scikit-learn 1.9.1. The workflow is offline; it reads the existing Phase 3A manifest and feature Parquet artifacts and performs no download.

## Staged execution

Run each stage separately and inspect its aggregate JSON before continuing:

```powershell
& '.\.venv\Scripts\python.exe' scripts/run_phase3b_review_ranking.py select-features
& '.\.venv\Scripts\python.exe' scripts/run_phase3b_review_ranking.py calibrate
& '.\.venv\Scripts\python.exe' scripts/run_phase3b_review_ranking.py evaluate
& '.\.venv\Scripts\python.exe' scripts/run_phase3b_review_ranking.py report
```

The access boundary is deliberate:

1. `select-features` reads January 1 and January 2 only.
2. `calibrate` refits references and models on January 1, compares methods on January 2, and writes a hashed frozen protocol.
3. `evaluate` verifies the configuration, feature-policy, reference, and frozen-protocol hashes before opening January 3.
4. `report` reads aggregate JSON only.

Use `--force` only for a deliberate reproducibility rerun. Never adjust configuration, feature selection, cutoff, or selected method after inspecting January 3.

## Artifacts

Committed aggregate evidence:

- `docs/qa/phase3b-feature-selection.json`
- `docs/qa/phase3b-calibration.json`
- `docs/qa/phase3b-evaluation.json`
- `docs/phase3b-baseline-comparison-report.md`

Ignored local row-level artifacts:

- `data/processed/review_ranking/calibration_rankings.parquet`
- `data/processed/review_ranking/test_rankings.parquet`

No fitted estimator is serialized. Isolation Forest is deterministically refitted from January 1 using the pinned configuration.

## Verification and privacy audit

```powershell
& '.\.venv\Scripts\python.exe' -m pytest -q
& '.\.venv\Scripts\python.exe' -m compileall -q apps scripts
& '.\.venv\Scripts\python.exe' scripts/run_phase3b_review_ranking.py --help
git status --short
git diff --check
git check-ignore data/processed/review_ranking/calibration_rankings.parquet
git check-ignore data/processed/review_ranking/test_rankings.parquet
```

Before staging, inspect names and sizes and scan public outputs for source identifiers, secrets, accusatory claims, unsupported model attribution, and accuracy-style metrics. Aggregate files must contain no `track_id` or `window_id`. Row-level rankings may contain date-scoped track/window surrogates only in ignored local storage; raw MMSI is forbidden.

## Interpretation limits

- January 3 is held out from Phase 3B fitting and calibration, but its aggregate Phase 3A QA was already known.
- Overlapping windows and repeated track observations are dependent.
- There are no ground-truth event labels, so accuracy, precision, recall, ROC-AUC, detection rate, and false-positive rate are not applicable.
- Rule and statistical reasons are exact feature components. Isolation Forest reasons are supporting feature evidence and are not model attribution.
- Review workload and concentration remain human-operational measurements, not evidence of real-world event prevalence.
