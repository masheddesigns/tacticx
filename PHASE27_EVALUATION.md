# TacticX Phase 27 — Prediction Evaluation Lifecycle

Contract Versions: `MATCH_OUTCOME_V1`, `PREDICTION_EVALUATION_V1`

## 1. Overview

Phase 27 measures how the production prediction system actually performs:

```
Prediction Snapshot (Phase 26, immutable)
        ↓
Match Completion (FINISHED + recorded scores)
        ↓
Verified Final Result → Outcome Snapshot (immutable, hashed)
        ↓
Prediction Evaluation (metrics vs verified outcome)
        ↓
Immutable Evaluation Record (idempotent on prediction+outcome)
        ↓
Aggregate Metrics / Calibration / Drift (read-only)
        ↓
Model Performance Dashboard
```

Measurement only. No model mathematics changed, no retraining, no weight
tuning, no promotion/demotion, no betting recommendations.

## 2. Evaluation Lifecycle & Outcome Provenance

Evaluation requires: existing prediction snapshot, match status
`FINISHED`, recorded home/away scores, and result temporally after the
prediction cutoff (guaranteed: predictions require cutoff < kickoff;
outcomes only exist for finished matches). Scheduled, postponed,
cancelled, suspended, abandoned, live, and scoreless matches refuse with
machine-readable codes (`MATCH_NOT_FINISHED`, `RESULT_SCORES_MISSING`).

Verified := canonical `FINISHED` result. There is no separate verification
flag in the schema; a canonical finished result is the verified outcome.
`capture_outcome_snapshot()` hashes the canonical payload
(match, goals, result, provider identity); repeats reuse the row; a
legitimately corrected score creates a new snapshot linked via
`supersedes_outcome_id`, which in turn creates a new evaluation version.
Old evaluations are never rewritten.

## 3. Metrics

Per-snapshot metrics reuse the Phase 2 primitive definitions
(`backtesting/metrics.py`: 1e-12 log-loss clipping, full-vector Brier):
1X2 accuracy / log loss / Brier; home/away/total goal errors and squared
errors (RMSE derived at aggregation); O/U 1.5/2.5/3.5 accuracy + log
loss + Brier; BTTS accuracy + log loss + Brier; exact-score hit, predicted
top score, and actual-score log probability. No new scoring methodology.

## 4. Immutability & Temporal Separation

Evaluation tables are separate from prediction tables with no cascading
writes; snapshots are opened read-only and their hash re-verified before
scoring. `evaluation_key` (hash of prediction_id + outcome_hash) carries
a DB unique constraint: repeats return the existing record; a changed
outcome hash creates a new version. Adversarial tests prove post-match
odds cannot enter the `PRE_MATCH` feature snapshot and prediction
payload/hash stay byte-identical after evaluation.

## 5. Calibration & Drift

Calibration reuses the Phase 2 equal-width reliability definition
(deterministic, `n_bins=10`): per-outcome (home/draw/away) predicted
probabilities vs observed frequencies plus count-weighted ECE. Empty
samples yield `ece: null`, never a crash.

Drift compares a trailing window (default recent 50) against the full
baseline with explicit sample sizes, periods, and per-metric differences.
Samples below 20 are flagged `sufficient_sample: false` instead of
concluding. No automatic degradation verdicts anywhere.

## 6. Scheduler

`post_match_evaluation` (priority 45, hourly): scans finished scored
matches, evaluates snapshots lacking an evaluation for the current
outcome, skips the rest. Incomplete matches are never evaluated; BLOCKED
concepts don't apply post-match (readiness was a pre-match gate).
Idempotency from the evaluation layer; locks/backoff from the existing
orchestrator.

## 7. API (read-only)

- `GET /matches/{id}/evaluation` — outcome, eligibility, evaluations.
- `GET /prediction-snapshots/{pid}/evaluation` — evaluations (empty list
  when unevaluated; never creates records).
- `GET /evaluations/summary` — filtered aggregates with period.
- `GET /evaluations/calibration` — reliability + ECE.
- `GET /evaluations/drift` — window vs baseline.
Record creation flows through the service + scheduler job only.

## 8. Frontend

`EvaluationSection` on the match page (completed matches with outcomes):
predicted vs actual, 1X2 hit/miss, log loss, Brier, goal MAE, market and
exact-score results. `ModelPerformanceSection` on the system page:
evaluated count, metric means, period, per-outcome ECE, drift deltas with
insufficient-sample notice. No model rankings.

## 9. Database

Migration `0012_evaluation_records` (head): `match_outcome_snapshots`
(14 cols) + `prediction_evaluation_records` (22 cols), FKs, unique
`outcome_id / (match,outcome_hash) / evaluation_id / evaluation_key /
evaluation_hash`, 25 indexes. Verified against real PostgreSQL 16.14:
fresh upgrade, downgrade to 0011, re-upgrade, idempotent re-run, and live
predict→finish→evaluate end-to-end with hash stability.
