# Phase 34 Design Audit — Controlled Candidate Validation

**Date**: 2026-09-23 · **Baseline**: `b4c685f` (Phase 33 CLOSED/READY) ·
Branch `main`. Alembic head: `0016_evidence`. Docker: unavailable.
Working tree note: `tests/test_phase30_governance.py` carries the
uncommitted Phase 32 chain-ownership edit (head assertion → linkage
assertion); it is included in the Phase 34 commit and noted in the
report. No other drift.

## 1. Reusable structures (no duplication)

| Need | Existing | Reuse |
|---|---|---|
| Research candidate/experiment/dataset identity | Phase 29 `ResearchCandidate/Dataset/Experiment`, `result_hash`, evidence states | read-only reads |
| Artifact identity + lifecycle | Phase 30 `ModelArtifact`, `artifact_hash`, transition map | read-only reads; NO new transitions |
| Research-evidence validation | Phase 30 `validate_candidate`, `check_compatibility`, immutable `ModelValidationReport` | called, not copied |
| Champion binding | Phase 30 `current_champion`, `resolve_active_model_id` | read-only reads |
| Paired evidence + states | Phase 33 `EvidenceCohort/Snapshot`, `generate_snapshot`, 7 states | read-only reads + recompute-verify |
| Uncertainty | Phase 28 Wilson + seeded bootstrap (via Phase 33 results) | read from snapshot, not recomputed |
| Anomaly signals | `production_monitoring.detect_anomalies` (CRITICAL count) | read-only call |
| Failure codes | `PredictionBlocked`/`EvaluationBlocked`/`OutcomeNotReady` families | mapped, not redefined |

## 2. What Phase 34 adds (and only this)

- Versioned `CandidateValidationConfig` registry (code-defined,
  documented rationale per threshold; no invented numbers without
  rationale — defaults conservative).
- Deterministic 14-rule engine over already-computed evidence.
- `candidate_validation_reports` table (binds candidate + champion +
  evidence snapshot + config; hash-pinned; immutable).
- Staleness check (champion/evidence/config drift ⇒ STALE).
- Read-only API/CLI/frontend surfaces + guarded run/refresh.
- No scheduler job (§39: manual invocation preferred; documented).

## 3. Threshold rationale (nothing invented silently)

- `min_paired_observations = 50`: governance handoff is a stronger
  claim than Phase 33 inference (20); 50 gives paired-bootstrap CIs
  practical width on log-loss differences. Configurable; requires
  human/domain sign-off for production use (recorded in config record).
- `max_exclusion_rate = 0.30`: above this, the paired set may no longer
  represent the cohort; configurable.
- `max_temporal_violation_rate = 0.0`: any contamination blocks (safety,
  not statistics).
- Allowed evidence states for handoff: SUPPORTED_DIFFERENCE,
  INCONCLUSIVE (neutral evidence is reviewable; DESCRIPTIVE_ONLY and
  below are not). Rationale: governance review judges fitness; the gate
  judges completeness + integrity. CONFLICTING (demonstrably worse on
  both metrics) stays INCONCLUSIVE at the gate — reviewable, not
  auto-rejected.
- Calibration required: AVAILABLE (recomputed payloads exist when
  n ≥ 10; below that the gate cannot verify output quality).

## 4. Authority boundary

Phase 34 writes only `candidate_validation_reports`. It never creates
promotion requests, approvals, shadow/canary states, activations, or
rollbacks; it never writes predictions, outcomes, evaluations,
evidence, or registry rows. Handoff = a human reads the report and
invokes the Phase 30 workflow explicitly.
