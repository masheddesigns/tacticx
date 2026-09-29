# Phase 32 Shadow Architecture

Contract: `SHADOW_EXECUTION_V1`

> Shadow evidence does not authorize production activation.

## 1. Data flow

```
REAL MATCH (SCHEDULED)
  ↓  get_latest_certificate (eligible state, cutoff < kickoff)
READINESS CERTIFICATE
  ↓  latest Phase 26 snapshot (champion authoritative, reused)
CHAMPION PREDICTION + PredictionFeatureSnapshot row (shared input F)
  ↓  challenger artifact must be in SHADOW state
CHALLENGER (research predict path, same cutoff, reads F)
  ↓  Phase 26 output validation + Phase 30 compatibility
SHADOW ROW (F id + hash, production prediction id, both outputs/hashes,
            shadow_execution_key UNIQUE)
  ↓  match finishes → shared Phase 27 outcome snapshot
CHAMPION EVALUATION (existing record) + CHALLENGER EVALUATION
(shadow_evaluation_records, same outcome hash)
  ↓  factual comparison (no winner)
```

## 2. Shared-input guarantee

`execute_shadow()` resolves the champion's stored feature snapshot row
and binds its id + hash into the shadow row; the challenger never
rebuilds features. `validate_shadow_pair()` verifies same match/
kickoff/cutoff/mode, feature id + hash equality against the stored
row, champion-prediction binding, and cutoff < kickoff. Mismatch →
`SHADOW_PAIR_INVALID`, never silent continuation.

## 3. Temporal guarantees

Cert cutoff < kickoff enforced before execution; champion prediction
cutoff must equal the latest cert cutoff (mixed inputs refused);
feature rows are pre-cutoff by Phase 26 construction; adversarial tests
prove post-cutoff odds/results/events/lineups cannot alter shadow
inputs or outputs.

## 4. Shadow lifecycle

Eligibility scan (`NO_ELIGIBLE_MATCHES` valid) → explicit execution
(API/CLI/scheduler, all guarded or read-only) → immutable row →
outcome linkage → persisted evaluation (`EVALUATED`). Re-execution
returns the existing row via `shadow_execution_key`. New cutoff/model/
features → new row; history untouched.

## 5. Outcome linkage & evaluation

Outcomes via Phase 27 `capture_outcome_snapshot` (shared identity, corrections
supersede). Champion scored via `evaluate_prediction_snapshot`;
challenger via identical `score_snapshot` into `shadow_evaluation_records`.
Comparison aggregates means + differences with denominators and
`INSUFFICIENT_DATA` below n=20.

## 6. Monitoring

Read-only `shadow_summary` (coverage, evaluation rate, per-challenger
counts) and `shadow_comparison` (aggregate diffs). No governance calls;
no promotion/demotion/rollback triggers exist in these paths.

## 7. Phase 30 integration

Challenger lifecycle (validate → request → approve → SHADOW), artifact
identity, audit trail, and rollback authority all reused unmodified.
Phase 32 adds no governance concepts — only shared-input execution and
persisted shadow evaluations.

## 8. Failure handling

Missing/invalid challenger, incompatible/invalid output, missing
feature row, cert/prediction mismatch, blocked/stale matches, unknown
matches, executor errors — all fail closed with codes; champion path
provably intact after every failure (tested).

## 9. Restart behavior

Deterministic execution key ⇒ interrupt + rerun yields the same row;
evaluation rerun yields the same record; no duplicate pairs; no
champion mutation.

## 10. Real-data limitations

0 real upcoming 2026/27 fixtures at measured sources ⇒ production-like
shadow reports `NO_ELIGIBLE_MATCHES` honestly. Synthetic fixtures exist
only in test DBs and never touch production tables (proven by
row-count assertions).
