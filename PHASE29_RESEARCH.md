# TacticX Phase 29 — Controlled Research Pipeline

Contracts: `RESEARCH_EXPERIMENT_V1` · Protocol: `cutoff_safe_walkforward v1`

## 1. Research architecture

`app/services/research/` (contracts, datasets, candidates, experiments,
isolation) is strictly separated from `prediction_execution`,
`production_monitoring`, `match_intelligence`, the scheduler, and model
directories. Candidates invoke existing production model classes
read-only through the identical cutoff-safe `predict()` path; no
production file, weight, config, feature, snapshot, evaluation, or
provider state is writable from research code.

## 2. Production isolation

`production_fingerprint()` hashes six locked model files plus the
`PredictionReadinessConfig` and registry keys; `verify_fingerprint()`
proves post-run intactness (tested across all four built-ins).
`ResearchExperiment` rows reference production only by id/hash strings
(no FKs). No `PRODUCTION` status exists anywhere in the lifecycle.

## 3. Experiment contract & dataset versioning

Experiments bind candidate + dataset + seed + code hash; re-runs return
the existing record. Datasets are explicit versioned observation lists
(match, cutoff) over FINNISH-scored matches with `kickoff_minus_24h`
cutoffs, provenance, and content hash; identical inputs reuse the row.
Chronological train/validation/test thirds are derived deterministically
from kickoff order; boundaries recorded in train/validation/test periods.

## 4. Temporal methodology

`audit_temporal_integrity()` verifies every cutoff precedes its kickoff
and splits are chronological. Candidate declared-input tables are
allowlisted against `CUTOFF_SAFE_TABLES`; violations mark the candidate
and any run `INVALID_EXPERIMENT` — recorded auditable, never scored.

## 5. Baseline reproduction

`baseline_repro` re-runs `ensemble_v1-elo+poisson` through the research
pipeline on the identical test observations: metrics bit-identical,
Δlogloss = Δbrier = 0.0, state `NO_CLEAR_DIFFERENCE`. Golden production
values unchanged (`0.60605 / 0.22233 / 0.17161`, `λ 1.7442 / 0.1713`).

## 6. Candidate methodology

Four controlled built-ins: baseline reproduction, poisson-only and
elo-only family alternatives, and a 60/40 ensemble weight variant.
Hypotheses, not improvements; each carries declared inputs, versions,
and code hash.

## 7. Comparison rules & uncertainty

Same observations, same cutoffs, same `score_snapshot` scoring for both
arms. Paired bootstrap (seed 7, n=2000) on log-loss/Brier via
`evaluation.compare.paired_metric_difference`; negative mean favors the
candidate. States: `INSUFFICIENT_EVIDENCE` (n < 20),
`IMPROVEMENT_EVIDENCE` (both CIs entirely below 0),
`REGRESSION_EVIDENCE` (both entirely above 0), else
`NO_CLEAR_DIFFERENCE`. No winner/best/recommended language anywhere.

## 8. Multiple-comparison protection

Every result records `family_experiment_count` plus a note that
selection across experiments must account for it; the registry lists all
experiments per candidate. No automatic promotion exists.

## 9. Reproducibility

Seed, dataset hash, feature/model/candidate versions, candidate + runner
code hashes, protocol version all persisted; re-runs return the identical
`result_hash`. Changing any semantic input changes the hash.

## 10. API / frontend / scheduler

`/research/*` endpoints (candidates, built-ins, datasets, experiments,
run with operational guard + explicit confirm, comparison) — read paths
open, execution guarded, promotion impossible. Research page shows
candidates, datasets, experiments, neutral comparison, reproducibility,
and leakage state. No scheduler integration by design
(`NO AUTOMATIC RESEARCH EXECUTION`).

## 11. Migration

`0013_research_registry` (head): three append-only tables, no production
FKs, unique hashes. Verified on real PostgreSQL 16.14 (fresh upgrade,
downgrade, re-upgrade, idempotent rerun) plus a live research run with
rerun determinism.

## 12. Limitations

Evidence about candidates, not production changes. Small-sample states
are explicit. Calibration is descriptive. Selection across many
experiments needs multiple-comparison discipline outside any single
result.
