# SeaWatch Phase 3B Explainable Review Ranking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and compare deterministic rule, robust statistical, and Isolation Forest baselines that rank accepted AIS windows for human review with factual explanations and strict date-split isolation.

**Architecture:** Load only hash-validated Phase 3A daily feature artifacts through role-gated readers, freeze a January 1 reference profile, calibrate workload and method selection on January 2, then apply one frozen protocol to January 3. Independent scorers share feature policy, preprocessing, ranking, explanation, and aggregate evaluation contracts; real row-level rankings and fitted state remain ignored and local.

**Tech Stack:** Python 3.12.7, pandas 3.0.6, NumPy 2.5.3, PyArrow 25.0.1, scikit-learn 1.9.1, pytest 9.1.1, JSON configuration/metadata, local Parquet rankings.

**Spec:** `docs/superpowers/specs/2026-09-30-phase3b-explainable-review-ranking-design.md`

## Global Constraints

- Start from exact Phase 3A commit `5200b4d` on a new local Phase 3B branch; do not push or add a remote unless separately authorized.
- Use the existing project `.venv` created from `C:\wu\python.exe`; install only into that environment and never modify global Python.
- Use only the Phase 3A dates and fixed roles: January 1 train/reference, January 2 calibration, January 3 held-out evaluation.
- Score only existing Phase 2 windows whose `window_quality_status` is `sufficient`; do not change Phase 1/2 features, segmentation, windowing, or artifacts.
- Do not open the January 3 feature artifact during feature selection, reference fitting, calibration, threshold selection, or demo-method selection.
- Fit every percentile, clipping bound, robust scale, and estimator on January 1 only. Use January 2 only for label-free calibration and method selection.
- Do not impute missing features with zero. Tier A missingness makes a window unscorable; Tier B is excluded unless its train/calibration support gate passes.
- Treat windows from one track as dependent. Bootstrap and sensitivity procedures operate on whole tracks, never independent windows.
- Use `review_priority_score`, `behavioral pattern requiring human review`, and factual evidence language. Never infer hostility, intent, illegality, danger, identity, or a confirmed anomaly.
- Do not report accuracy, precision, recall, F1, ROC-AUC, false-positive rate, prevalence, or detection rate without ground-truth labels.
- Do not implement Transformers, LSTMs, GNNs, autoencoders, embeddings, LLM explanations, API endpoints, UI, persistence, feedback learning, deployment, logistics, or new data acquisition.
- Keep real ranked windows, reference profiles, calibration protocols, evaluation payloads, fitted estimators, raw AIS, and feature Parquet local and ignored. Commit only code, pinned configuration/dependencies, tests, docs, aggregate identifier-free QA JSON, and tiny synthetic fixtures.

## Review Focus

- A calibration command given an evaluation path, alias, or misleading filename must fail before reading it; Task 2 tests role-gated artifact access with a reader spy.
- A constant or nearly constant feature and a batch of tied scores must not cause division by zero or nondeterministic ranking; Tasks 3 and 4 pin scale fallbacks and the full tie order.
- A sparse feature present in many windows from only one track must fail the Tier B gate; Task 2 tests window support and track support independently.
- Whole-track bootstrap resamples may repeat clusters but must never split a track or accidentally treat duplicated track IDs as one draw; Task 7 tests draw-instance relabeling and member preservation.
- Isolation Forest rankings must remain deterministic in the pinned environment and explanations must not masquerade as model attribution; Tasks 6 and 7 test fixed seeds, `n_jobs=1`, score ordering, and reason labels.

---

### Task 1: Phase 3B configuration, language policy, and core contracts

**Files:**
- Modify: `requirements.txt`
- Create: `config/phase3b_review_ranking_v1.json`
- Create: `apps/api/seawatch/review_ranking/__init__.py`
- Create: `apps/api/seawatch/review_ranking/contracts.py`
- Create: `apps/api/seawatch/review_ranking/config.py`
- Create: `tests/unit/test_review_ranking_config.py`

**Interfaces:**
- Produces: `FeatureTier = Literal["A", "B", "C"]` and `TailDirection = Literal["high", "low", "two_sided"]`.
- Produces: immutable `FeaturePolicySpec`, `ReferenceSettings`, `RuleSettings`, `IsolationForestSettings`, `CalibrationSettings`, and `Phase3BConfig` dataclasses.
- Produces: `load_phase3b_config(path: Path) -> Phase3BConfig` and `phase3b_config_sha256(path: Path) -> str`.
- Produces: `EvidenceReason`, `ScoreFrame`, `ReferenceProfile`, `FeaturePolicyAnalysis`, and `CalibrationProtocol` aggregate dataclasses used by Tasks 2-8.
- Configures: exact Tier A/B/C lists, feature groups, units/directions, support gates, 1%/99% clipping, rule 5%/95% boundaries, top-20 primary budget, budgets 10/20/50, 100 bootstrap replicates, and Isolation Forest parameters from the spec.

- [ ] **Step 1: Write failing strict-configuration tests**

  Assert the committed JSON loads to the exact immutable values, includes each
  Phase 2 feature exactly once, uses only known units/directions, and rejects
  missing keys, unknown keys, overlapping tiers/groups, an invalid quantile,
  a non-positive budget, an unsupported feature name, and prohibited output
  phrases. Assert `requirements.txt` pins `scikit-learn==1.9.1`.

- [ ] **Step 2: Run the tests and verify RED**

  Run: `& '.\.venv\Scripts\python.exe' -m pytest tests/unit/test_review_ranking_config.py -v`

  Expected: FAIL because the configuration package and file do not exist.

- [ ] **Step 3: Add the pinned dependency and exact config**

  Add only `scikit-learn==1.9.1` to direct dependencies. Define the committed
  config with schema `phase3b-review-ranking-config-v1`, `random_state=42`,
  `n_jobs=1`, and fixed safety-language templates; do not install or implement
  a scorer in this task.

- [ ] **Step 4: Implement the strict loader and dataclasses**

  Implement the interfaces above with finite/range/type validation, complete
  Phase 2 feature coverage, disjoint tiers, disjoint behavioral groups, and
  fail-closed unknown-key handling.

- [ ] **Step 5: Install locally and verify GREEN**

  Run:

  ```powershell
  & '.\.venv\Scripts\python.exe' -m pip install -r requirements.txt
  & '.\.venv\Scripts\python.exe' -m pytest tests/unit/test_review_ranking_config.py -v
  ```

  Expected: scikit-learn 1.9.1 imports under Python 3.12.7 and all config tests pass.

- [ ] **Step 6: Commit Task 1**

  ```powershell
  git add requirements.txt config/phase3b_review_ranking_v1.json apps/api/seawatch/review_ranking/__init__.py apps/api/seawatch/review_ranking/contracts.py apps/api/seawatch/review_ranking/config.py tests/unit/test_review_ranking_config.py
  git commit -m "feat: define Phase 3B review ranking contract"
  ```

### Task 2: Role-gated input loading and pre-model feature analysis

**Files:**
- Create: `apps/api/seawatch/review_ranking/data.py`
- Create: `apps/api/seawatch/review_ranking/feature_policy.py`
- Create: `tests/unit/test_review_ranking_data.py`
- Create: `tests/unit/test_feature_policy.py`

**Interfaces:**
- Consumes: Phase 3A cohort schema `phase3a-multiday-v1`, Phase 2 window schema, and `Phase3BConfig` from Task 1.
- Produces: `SplitWindows(source_date: date, split_role: str, artifact_path: Path, artifact_sha256: str, frame: pd.DataFrame)`.
- Produces: `load_split_windows(cohort_manifest_path: Path, requested_roles: tuple[str, ...], *, root: Path) -> dict[str, SplitWindows]`.
- Produces: `analyze_feature_policy(train: SplitWindows, calibration: SplitWindows, config: Phase3BConfig) -> FeaturePolicyAnalysis`.
- Produces: `feature_policy_payload(analysis: FeaturePolicyAnalysis, *, input_hashes: Mapping[str, str], config_sha256: str) -> dict[str, object]`.

- [ ] **Step 1: Write failing role-gated loader tests**

  Create a tiny three-date cohort with three Parquet artifacts. Assert a
  request for `("train", "calibration")` opens only those two paths, verifies
  manifest/artifact hashes and immutable roles, retains only `sufficient`
  windows for scoring, and reports rejected counts separately. Use a patched
  reader that raises if the test artifact is touched.

- [ ] **Step 2: Add fail-closed input tests**

  Parameterize failures for changed split role, wrong date, wrong config hash,
  hash/size/row mismatch, duplicate date, forbidden public column, non-UTC
  timestamp, missing quality status, unknown requested role, and an explicit
  evaluation path supplied to a train/calibration-only call.

- [ ] **Step 3: Run loader tests and verify RED**

  Run: `& '.\.venv\Scripts\python.exe' -m pytest tests/unit/test_review_ranking_data.py -v`

  Expected: FAIL because `data.py` does not exist.

- [ ] **Step 4: Implement role-gated loading**

  Validate cohort and Phase 2 provenance before reading a requested artifact.
  Return only requested roles; do not resolve or stat an unrequested test path.
  Preserve identifiers needed for local ranking but never expose raw source IDs.

- [ ] **Step 5: Write failing feature-policy tests**

  Assert Tier A passes only at 95% finite support on both roles and with two
  distinct train values. Assert Tier B requires 80% support, 200 windows, 10
  tracks, and no greater than 10 percentage-point train/calibration gap.
  Include a fixture with 500 finite windows from one track and prove it fails.
  Assert Tier C is always excluded and no January 3 input is accepted.

- [ ] **Step 6: Implement feature-policy analysis**

  Measure finite window and track support, units, ranges, and exclusion reasons
  without fitting any transformation. Fail if a configured Tier A feature is
  ineligible; mark Tier B enabled/disabled with evidence; preserve Tier C as
  excluded. Serialize aggregate counts only.

- [ ] **Step 7: Run Task 2 tests and verify GREEN**

  Run: `& '.\.venv\Scripts\python.exe' -m pytest tests/unit/test_review_ranking_data.py tests/unit/test_feature_policy.py -v`

  Expected: all pass and the reader spy proves no test access.

- [ ] **Step 8: Commit Task 2**

  ```powershell
  git add apps/api/seawatch/review_ranking/data.py apps/api/seawatch/review_ranking/feature_policy.py tests/unit/test_review_ranking_data.py tests/unit/test_feature_policy.py
  git commit -m "feat: gate Phase 3B features and split access"
  ```

### Task 3: Train-only reference profile and robust transformations

**Files:**
- Create: `apps/api/seawatch/review_ranking/reference.py`
- Create: `tests/unit/test_review_reference.py`

**Interfaces:**
- Consumes: train `SplitWindows`, active feature names from `FeaturePolicyAnalysis`, and `ReferenceSettings`.
- Produces: `fit_reference_profile(train: SplitWindows, policy: FeaturePolicyAnalysis, config: Phase3BConfig) -> ReferenceProfile`.
- Produces: `empirical_midrank(values: np.ndarray, reference_sorted: np.ndarray) -> np.ndarray`.
- Produces: `transform_with_reference(frame: pd.DataFrame, profile: ReferenceProfile) -> TransformedFeatures` containing aligned raw, clipped, robust-scaled, percentile, and missing masks.
- Produces: `reference_profile_payload(profile: ReferenceProfile, *, train_hash: str, policy_hash: str, config_hash: str) -> dict[str, object]`.

- [ ] **Step 1: Write failing reference-statistic tests**

  Use synthetic skewed, tied, extreme, and constant features. Assert exact
  1st/99th train bounds, medians, IQR scale, MAD fallback, constant-feature
  exclusion, deterministic mid-ranks, and feature ordering from configuration.

- [ ] **Step 2: Write leakage and missingness tests**

  Add extreme calibration/test sentinel values and prove fitted profile values
  do not change. Assert transformations apply train bounds unchanged, retain
  original display values, reject non-finite Tier A inputs, and never produce
  zero merely because an input was missing.

- [ ] **Step 3: Run tests and verify RED**

  Run: `& '.\.venv\Scripts\python.exe' -m pytest tests/unit/test_review_reference.py -v`

  Expected: FAIL because `reference.py` does not exist.

- [ ] **Step 4: Implement reference fitting and transformations**

  Use stable sorted arrays for empirical CDF, `IQR / 1.349` before
  `1.4826 * MAD`, and explicit inactive reasons. Validate feature order and
  finite outputs. The fit signature accepts no calibration/evaluation frame.

- [ ] **Step 5: Run tests and verify GREEN**

  Run: `& '.\.venv\Scripts\python.exe' -m pytest tests/unit/test_review_reference.py -v`

  Expected: all pass.

- [ ] **Step 6: Commit Task 3**

  ```powershell
  git add apps/api/seawatch/review_ranking/reference.py tests/unit/test_review_reference.py
  git commit -m "feat: add train-only behavioral reference profile"
  ```

### Task 4: Shared deterministic ranking, explanations, and rule baseline

**Files:**
- Create: `apps/api/seawatch/review_ranking/ranking.py`
- Create: `apps/api/seawatch/review_ranking/explanations.py`
- Create: `apps/api/seawatch/review_ranking/rules.py`
- Create: `tests/unit/test_review_ranking.py`
- Create: `tests/unit/test_review_explanations.py`
- Create: `tests/unit/test_rule_baseline.py`

**Interfaces:**
- Produces: `rank_method_scores(metadata: pd.DataFrame, scores: ScoreFrame, *, review_budget: int, calibration_cutoff: float | None) -> pd.DataFrame`.
- Produces: `score_rule_baseline(features: TransformedFeatures, profile: ReferenceProfile, config: Phase3BConfig) -> ScoreFrame`.
- Produces: `build_evidence_reasons(method_id: str, score_components: pd.DataFrame, features: TransformedFeatures, config: Phase3BConfig) -> list[tuple[EvidenceReason, ...]]`.
- Produces ranked schema `phase3b-review-ranking-v1` with structured reasons, quality fields, and no source identifiers.

- [ ] **Step 1: Write failing ranking-contract tests**

  Assert scores are finite in `[0, 100]`, exactly top 20 are shortlisted when
  at least 20 rows exist, smaller inputs shortlist all rows, and ties sort by
  score descending then UTC, `track_id`, and `window_id`. Run a fully tied
  fixture twice and assert byte-identical serialized order.

- [ ] **Step 2: Write failing explanation and language tests**

  Assert every shortlisted item has at least one structured reason with value,
  unit, direction, severity, and January 1 comparison. Assert a three-reason
  cap, fixed templates, no raw source identifiers, and no prohibited intent,
  legality, danger, or confirmed-anomaly words in schema values/messages.

- [ ] **Step 3: Write failing rule-score tests**

  Pin high-tail and low-tail behavior at the 5th/95th boundaries, exact linear
  severity, group maximum aggregation, conditional rules disabled by policy,
  and a fixture where correlated features do not double the group weight.

- [ ] **Step 4: Run tests and verify RED**

  Run: `& '.\.venv\Scripts\python.exe' -m pytest tests/unit/test_review_ranking.py tests/unit/test_review_explanations.py tests/unit/test_rule_baseline.py -v`

  Expected: FAIL because the three modules do not exist.

- [ ] **Step 5: Implement ranking and explanations**

  Centralize the schema and tie-breaker. Store reasons as validated tuples in
  memory and deterministic JSON in Parquet-compatible output. Label rule and
  statistical reasons `exact_component`; reserve `supporting_evidence` for IF.

- [ ] **Step 6: Implement the rule scorer**

  Implement the five configured rule codes, with turning/irregularity active
  only when their Tier B features pass. Use original values for messages and
  reference percentiles for severity.

- [ ] **Step 7: Run tests and verify GREEN**

  Run the Task 4 command again. Expected: all pass.

- [ ] **Step 8: Commit Task 4**

  ```powershell
  git add apps/api/seawatch/review_ranking/ranking.py apps/api/seawatch/review_ranking/explanations.py apps/api/seawatch/review_ranking/rules.py tests/unit/test_review_ranking.py tests/unit/test_review_explanations.py tests/unit/test_rule_baseline.py
  git commit -m "feat: rank review candidates with transparent rules"
  ```

### Task 5: Empirical-percentile and robust-MAD baselines

**Files:**
- Create: `apps/api/seawatch/review_ranking/statistics.py`
- Create: `tests/unit/test_statistical_baselines.py`

**Interfaces:**
- Consumes: `TransformedFeatures`, `ReferenceProfile`, active feature groups, and shared explanation/ranking contracts.
- Produces: `score_percentile_baseline(features: TransformedFeatures, config: Phase3BConfig) -> ScoreFrame`.
- Produces: `score_robust_mad_baseline(features: TransformedFeatures, config: Phase3BConfig) -> ScoreFrame`.
- Produces: `ordinary_z_diagnostics(train: pd.DataFrame, later: pd.DataFrame, feature_names: tuple[str, ...]) -> dict[str, object]`; diagnostics never enter ranking.

- [ ] **Step 1: Write failing percentile-score tests**

  Assert two-sided extremeness `2 * abs(p - 0.5)`, within-group maximum, and
  `0.7 * largest + 0.3 * second_largest` across groups. Pin exact results for
  central, one-tail, and two-group fixtures and deterministic behavior under
  tied reference values.

- [ ] **Step 2: Write failing robust-MAD tests**

  Assert severity `1 - exp(-abs(clipped - median) / scale)`, shared group
  aggregation, finite bounds, and inactive constant-feature behavior. Assert
  no calibration-derived center/scale is accepted.

- [ ] **Step 3: Write diagnostic z-score tests**

  Assert ordinary z diagnostics report zero standard deviation and outlier
  sensitivity safely but never produce a `ScoreFrame` or a shortlist.

- [ ] **Step 4: Run tests and verify RED**

  Run: `& '.\.venv\Scripts\python.exe' -m pytest tests/unit/test_statistical_baselines.py -v`

  Expected: FAIL because `statistics.py` does not exist.

- [ ] **Step 5: Implement statistical scorers and diagnostics**

  Use the exact formulas above, preserve configured feature/group order, and
  emit exact component severities for shared explanation generation.

- [ ] **Step 6: Run tests and verify GREEN**

  Run the Task 5 command again. Expected: all pass.

- [ ] **Step 7: Commit Task 5**

  ```powershell
  git add apps/api/seawatch/review_ranking/statistics.py tests/unit/test_statistical_baselines.py
  git commit -m "feat: add robust statistical review baselines"
  ```

### Task 6: Deterministic Isolation Forest comparison

**Files:**
- Create: `apps/api/seawatch/review_ranking/isolation_forest.py`
- Create: `tests/unit/test_isolation_forest_baseline.py`

**Interfaces:**
- Consumes: clipped robust-scaled active `TransformedFeatures` (Tier A plus any
  gated Tier B features) in frozen order shared with the transparent methods.
- Produces: `FittedIsolationForest(estimator: IsolationForest, feature_names: tuple[str, ...], train_raw_scores_sorted: np.ndarray, parameter_hash: str)`.
- Produces: `fit_isolation_forest(train: TransformedFeatures, config: Phase3BConfig) -> FittedIsolationForest`.
- Produces: `score_isolation_forest(model: FittedIsolationForest, features: TransformedFeatures, config: Phase3BConfig) -> ScoreFrame`.

- [ ] **Step 1: Write failing fixed-parameter tests**

  Assert the estimator receives 256 trees, `max_samples="auto"`, all features,
  no bootstrap, `contamination="auto"`, seed 42, and one job. Reject a feature
  order mismatch, NaN, infinity, or a changed active feature set.

- [ ] **Step 2: Write deterministic ranking tests**

  Fit the same synthetic training matrix twice and assert identical raw scores,
  training-percentile scores, ranking order, and parameter hash. Assert no
  `predict()` classification or anomaly label appears in output.

- [ ] **Step 3: Write explanation-semantics tests**

  Assert IF reasons use the largest empirical Tier A deviations, are labeled
  `supporting_evidence`, include a non-attribution disclaimer, and never claim
  to explain a tree path or infer behavior intent.

- [ ] **Step 4: Run tests and verify RED**

  Run: `& '.\.venv\Scripts\python.exe' -m pytest tests/unit/test_isolation_forest_baseline.py -v`

  Expected: FAIL because the adapter does not exist.

- [ ] **Step 5: Implement the adapter**

  Wrap scikit-learn behind the interfaces above. Use `-score_samples`, convert
  through the fitted training empirical CDF, and never serialize the estimator
  or expose `predict()`.

- [ ] **Step 6: Run tests and verify GREEN**

  Run the Task 6 command again. Expected: all pass.

- [ ] **Step 7: Commit Task 6**

  ```powershell
  git add apps/api/seawatch/review_ranking/isolation_forest.py tests/unit/test_isolation_forest_baseline.py
  git commit -m "feat: compare deterministic Isolation Forest rankings"
  ```

### Task 7: Track-aware calibration, robustness, and label-free evaluation

**Files:**
- Create: `apps/api/seawatch/review_ranking/evaluation.py`
- Create: `tests/unit/test_review_evaluation.py`

**Interfaces:**
- Consumes: named scorer factories from Tasks 4-6, train/calibration split windows, shared ranking output, and calibration settings.
- Produces: `cluster_bootstrap_track_draws(track_ids: pd.Series, *, replicates: int, seed: int) -> tuple[tuple[BootstrapTrackDraw, ...], ...]` where repeated draws receive unique draw-instance IDs but retain all source windows.
- Produces: `evaluate_stability(...) -> StabilityMetrics`, `evaluate_robustness(...) -> RobustnessMetrics`, and `evaluate_workload(...) -> WorkloadMetrics`.
- Produces: `calibrate_methods(train: SplitWindows, calibration: SplitWindows, policy: FeaturePolicyAnalysis, profile: ReferenceProfile, config: Phase3BConfig) -> CalibrationProtocol`.
- Produces: `evaluate_frozen_protocol(train: SplitWindows, evaluation: SplitWindows, protocol: CalibrationProtocol, config: Phase3BConfig) -> EvaluationSummary`.

- [ ] **Step 1: Write failing track-bootstrap tests**

  Construct unequal track sizes. Assert each draw samples track clusters with
  replacement, includes every window of a drawn track, relabels repeated draw
  instances, never mixes partial tracks, and is deterministic for the seed.

- [ ] **Step 2: Write failing metric tests**

  Pin top-10/20/50 Jaccard, Spearman rank correlation, score variation,
  distinct-track count, maximum track share, reason coverage, score-cutoff
  exceedance, and workload reduction. Assert empty/small shortlists return
  declared nulls rather than invented zeros.

- [ ] **Step 3: Write failing calibration-selection tests**

  Build four synthetic method results. Assert the hard gates are exact, the
  highest median top-20 Jaccard wins, a difference below 0.05 follows
  percentile/rule/MAD/IF transparency precedence, and the stored cutoff is the
  calibration rank-20 score. Assert no labels are accepted by the interface.

- [ ] **Step 4: Write failing frozen-evaluation tests**

  Assert evaluation rejects a missing or mismatched protocol/config/reference
  hash, cannot alter method/threshold/feature order, scores January 3 once, and
  reports cutoff transfer separately from the exact top-20 review workload.

- [ ] **Step 5: Run tests and verify RED**

  Run: `& '.\.venv\Scripts\python.exe' -m pytest tests/unit/test_review_evaluation.py -v`

  Expected: FAIL because `evaluation.py` does not exist.

- [ ] **Step 6: Implement cluster-aware evaluation**

  Use 100 fixed whole-track resamples. Implement the declared robustness grid
  without reading evaluation data. Store every variant and seed in aggregate
  metadata; calibration selects only under the frozen rubric.

- [ ] **Step 7: Implement frozen evaluation**

  Refit the selected method from January 1 and verify its reference hash, apply
  to January 3 once, then compute descriptive transfer, agreement, reasons,
  concentration, and workload. Do not recompute any learned statistic on test.

- [ ] **Step 8: Run tests and verify GREEN**

  Run the Task 7 command again. Expected: all pass.

- [ ] **Step 9: Commit Task 7**

  ```powershell
  git add apps/api/seawatch/review_ranking/evaluation.py tests/unit/test_review_evaluation.py
  git commit -m "feat: calibrate and evaluate review rankings without labels"
  ```

### Task 8: Atomic artifacts, staged offline CLI, and synthetic workflow

**Files:**
- Create: `apps/api/seawatch/review_ranking/io.py`
- Create: `apps/api/seawatch/review_ranking/pipeline.py`
- Create: `scripts/run_phase3b_review_ranking.py`
- Create: `tests/integration/test_phase3b_review_cli.py`
- Create: `tests/integration/test_phase3b_synthetic_pipeline.py`
- Modify: `.gitignore`

**Interfaces:**
- Produces: CLI subcommands `select-features`, `calibrate`, `evaluate`, and `report`.
- Produces: `preflight_phase3b_outputs(outputs: Iterable[Path], *, inputs: Iterable[Path], overwrite: bool) -> None`.
- Produces: `write_rankings(frame: pd.DataFrame, path: Path, provenance: Mapping[str, str], *, overwrite: bool = False) -> ArtifactRecord`.
- Produces: aggregate JSON schemas `phase3b-feature-policy-v1`, `phase3b-calibration-v1`, and `phase3b-evaluation-v1`.
- Produces: `render_phase3b_report(...) -> str` with no row identifiers.

- [ ] **Step 1: Add ignored local artifact paths and failing IO tests**

  Ignore `data/processed/review_ranking/*` except `.gitkeep`. Test final,
  `.partial`, duplicate, and input/output alias collisions before reads/writes;
  metadata presence; forbidden identifiers; atomic replacement; and cleanup on
  malformed input.

- [ ] **Step 2: Write failing stage-boundary CLI tests**

  Assert `select-features` accepts only train/calibration and emits a policy;
  `calibrate` requires its hash and emits a frozen protocol without reading
  test; `evaluate` requires matching policy/protocol hashes and may then read
  test; `report` consumes aggregate metadata only. Patch every network entry
  point to raise.

- [ ] **Step 3: Write the synthetic three-date integration test**

  Flow small feature fixtures through all four methods and stages. Assert
  deterministic top-20 behavior, split isolation, identical train reference
  hashes, calibration-only selection, frozen evaluation, 100% explanation
  coverage, no labels/accuracy metrics, and no prohibited language or IDs in
  aggregate outputs.

- [ ] **Step 4: Run integration tests and verify RED**

  Run: `& '.\.venv\Scripts\python.exe' -m pytest tests/integration/test_phase3b_review_cli.py tests/integration/test_phase3b_synthetic_pipeline.py -v`

  Expected: FAIL because IO, pipeline, and CLI do not exist.

- [ ] **Step 5: Implement atomic IO and pipeline orchestration**

  Keep each stage narrow. Write payloads only after full validation and use
  final-plus-`.partial` atomic behavior. Ranking Parquet contains public-safe
  row data; report/QA JSON contains aggregates only.

- [ ] **Step 6: Implement the four CLI subcommands**

  Default to the Phase 3A cohort manifest and ignored Phase 3B output folder.
  Require explicit `--force`; print input/output hashes and selected method;
  perform no network access.

- [ ] **Step 7: Run integration and full offline tests**

  Run:

  ```powershell
  & '.\.venv\Scripts\python.exe' -m pytest tests/integration/test_phase3b_review_cli.py tests/integration/test_phase3b_synthetic_pipeline.py -v
  & '.\.venv\Scripts\python.exe' -m pytest -q
  ```

  Expected: all pass without network access.

- [ ] **Step 8: Commit Task 8**

  ```powershell
  git add .gitignore apps/api/seawatch/review_ranking/io.py apps/api/seawatch/review_ranking/pipeline.py scripts/run_phase3b_review_ranking.py tests/integration/test_phase3b_review_cli.py tests/integration/test_phase3b_synthetic_pipeline.py
  git commit -m "feat: add staged offline review ranking workflow"
  ```

### Task 9: Reproducible runbook and explicit real-data comparison

**Files:**
- Create: `docs/phase3b-review-ranking-runbook.md`
- Create after measurement: `docs/qa/phase3b-feature-selection.json`
- Create after measurement: `docs/qa/phase3b-calibration.json`
- Create after measurement: `docs/qa/phase3b-evaluation.json`
- Create after measurement: `docs/phase3b-baseline-comparison-report.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: Task 8 CLI and existing ignored Phase 3A feature Parquet files.
- Produces: identifier-free aggregate evidence and a demo-method decision; no model binary or real ranking artifact is committed.

- [ ] **Step 1: Write the runbook before executing real stages**

  Document environment verification, input/hash checks, the separate
  `select-features`, `calibrate`, human inspection, `evaluate`, and `report`
  commands, ignored artifacts, privacy scans, limitations, and the requirement
  to stop before API/UI work.

- [ ] **Step 2: Verify Phase 3A inputs read-only**

  Re-run the Phase 3A independent audit, verify all three feature hashes and
  config hash, and confirm no additional date exists. Stop on discrepancy.

- [ ] **Step 3: Run feature selection without opening January 3**

  Execute `select-features`, inspect the access log and output hashes, and
  confirm the actual Tier decisions. If Tier A fails or unexpected Tier B
  support passes, stop for review rather than silently changing the model.

- [ ] **Step 4: Calibrate all methods on January 2**

  Execute `calibrate`; record per-method stability, robustness, reason coverage,
  workload/concentration, score cutoff, hard-gate results, and selected demo
  method. Inspect and freeze the protocol before evaluation.

- [ ] **Step 5: Run one frozen January 3 evaluation**

  Execute `evaluate` once with the reviewed protocol hash. Record the exact
  top-20 workload, calibration-cutoff exceedance, method agreement, reason
  distribution, track concentration, and temporal shifts. Do not retune.

- [ ] **Step 6: Generate aggregate artifacts and report**

  Run `report`. Confirm the three JSON files and Markdown contain no individual
  `track_id` or `window_id`, prohibited claims, accuracy metrics, or inferred
  labels. Include the limitation that January 3 aggregate QA was visible in
  Phase 3A and that windows/vessels are dependent.

- [ ] **Step 7: Independently reproduce and audit**

  Re-run the full workflow into a separate ignored directory and compare
  policy/protocol/evaluation hashes, rankings, explanations, selected method,
  and aggregate report byte-for-byte. Recompute top-K and every reported
  metric directly from local artifacts.

- [ ] **Step 8: Update README and commit aggregate documentation**

  Link the runbook and report, state that outputs prioritize human review and
  do not classify threats, and stage no real row-level ranking or fitted state.

  ```powershell
  git add README.md docs/phase3b-review-ranking-runbook.md docs/phase3b-baseline-comparison-report.md docs/qa/phase3b-feature-selection.json docs/qa/phase3b-calibration.json docs/qa/phase3b-evaluation.json
  git commit -m "docs: record Phase 3B baseline comparison"
  ```

### Task 10: Final regression, scope, artifact, and language audit

**Files:**
- Modify only files required to correct a verified failure.

**Interfaces:**
- Verifies the complete Phase 3B branch; introduces no new behavior.

- [ ] **Step 1: Run full verification from the final tree**

  ```powershell
  & '.\.venv\Scripts\python.exe' -m pytest -q
  & '.\.venv\Scripts\python.exe' -m compileall -q apps scripts
  & '.\.venv\Scripts\python.exe' scripts/run_phase3b_review_ranking.py --help
  ```

  Expected: all tests pass, compilation succeeds, help exits zero, and tests
  perform no network calls.

- [ ] **Step 2: Repeat split and leakage audits**

  Prove from access logs and artifact provenance that train alone fitted every
  reference/model, calibration alone selected the cutoff/method, and January 3
  was read only after the frozen protocol. Verify no cross-date rows or hashes.

- [ ] **Step 3: Audit claims and metrics**

  Scan executable output, aggregate JSON, reports, and synthetic examples for
  hostile/illegal/dangerous/suspicious/malicious/confirmed-anomaly claims,
  accuracy-style metrics, raw identifiers, unsupported attributions, and
  missing-to-zero behavior. Documentation may name forbidden terms only while
  declaring their prohibition.

- [ ] **Step 4: Audit Git and artifacts explicitly**

  Run `git status --short`, `git diff --check`, staged name/size/numstat checks,
  `git check-ignore` on ranking/reference/protocol/model artifacts, a secret
  scan, `git log` from `5200b4d`, and `git remote -v`. Confirm no Parquet,
  pickle, joblib, model binary, database, raw AIS, or large artifact is staged.

- [ ] **Step 5: Report success criteria and stop**

  Report starting SHA, branch, dependency/config hashes, Tier decisions,
  per-method calibration metrics, selected method and rationale, frozen cutoff,
  held-out workload/transfer metrics, explanation coverage, reproducibility,
  tests, artifact/privacy audit, commits, failures/deviations, and known limits.
  Stop before API, UI, persistence, feedback learning, new dates, or any deeper
  model.
