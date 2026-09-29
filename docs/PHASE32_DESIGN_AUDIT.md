# Phase 32 Design Audit — Real-Data Champion/Challenger Shadow

**Date**: 2026-09-23 · **Baseline**: `f87c334` (Phase 31 CLOSED/READY) ·
Branch `main`, clean tree. Alembic head: `0014_model_governance`.
Docker: unavailable on this machine (boundary carried from Phase 31).

## 1. What Phase 30 already provides

- `ShadowPredictionSnapshot` table (shadow_id unique, match, both
  artifact ids, cutoff, both outputs + hashes, created_at) and
  `run_shadow_pair()` (isolated pair execution, no prod writes),
  `start_shadow()` (APPROVED-gated), `evaluate_shadow()` (factual
  scoring via Phase 27 `score_snapshot`), `shadow_pairs()` listing.
- Full governance: artifact registry, lifecycle machine, validation,
  promotion requests, counted approvals, canary checklist, activation
  with optimistic concurrency, rollback, audit trail.
- `run_shadow_pair` recomputes both models fresh and hashes a synthetic
  feature key — it does NOT reference Phase 26 feature snapshots or
  production predictions. Left intact (its tests depend on it).

## 2. What Phase 32 adds

- **Shared feature snapshot binding**: shadow execution resolves the
  champion's Phase 26 `PredictionFeatureSnapshot` (same
  `snapshot_id`/`snapshot_hash`) and the champion's production
  prediction (`production_prediction_id`); the challenger runs against
  that identical input. New columns on `shadow_prediction_snapshots`
  + deterministic `shadow_execution_key` (UNIQUE) for idempotency.
- **Persisted shadow evaluations**: new `shadow_evaluation_records`
  (champion + challenger metrics vs the SAME outcome snapshot,
  differences, hashes). Phase 27 record shape mirrored, separate table.
- **Orchestration package** `app/services/shadow_execution/` (new;
  Phase 30 untouched): eligibility, shared-snapshot execution, pair
  validation (`validate_shadow_pair` → SHADOW_PAIR_INVALID), outcome
  linkage, evaluation, read-only monitoring metrics.
- **Scheduler job** `shadow_prediction` (9th type): eligible real
  matches only; never activates/requests/promotes; NO_ELIGIBLE_MATCHES
  is a valid result.
- **API `/shadow/*`** (new router; no conflicts), **CLI `shadow`**
  (7 commands, service reuse), **frontend `/shadow`** + nav.
- **Migration 0015** (ALTER + CREATE, safe conventions).

## 3. Where predictions originate

- Champion: Phase 26 `execute_pre_match_prediction` ONLY (existing
  snapshots reused; never recomputed for shadow).
- Challenger: research `predict_with_candidate` (read-only model-class
  invocation, cutoff-safe path) for a SHADOW-state artifact.

## 4. Shared-input guarantee

`validate_shadow_pair()`: same match/kickoff/cutoff/mode, feature
snapshot id + hash equality between the champion's stored snapshot row
and the shadow row, schema compatibility of both outputs. The shadow
row stores `feature_snapshot_id`; the Phase 26 feature row is read,
never rewritten.

## 5. Isolation & production safety

Phase 30 shadow writes + Phase 32 writes touch only shadow tables.
Production snapshots/intelligence/registry/outcomes/evaluations are
opened read-only. Scheduler/API/CLI paths contain no activation,
promotion-request, or registry-write calls (verified by tests +
inspection). Adversarial tests cover all §31/§34/§40 cases.

## 6. Outcome linkage & evaluation

Outcomes via Phase 27 `capture_outcome_snapshot` (shared identity);
champion scored via `evaluate_prediction_snapshot` (existing record);
challenger scored via `score_snapshot` into `shadow_evaluation_records`
(same implementation, same outcome hash). Corrections supersede per
Phase 27; shadow re-evaluation versions explicitly.

## 7. Test strategy

Isolated synthetic fixtures in test DBs only (never production paths);
`NO_ELIGIBLE_MATCHES` unit + API coverage; restart/idempotency via
re-execution; migration lifecycle on SQLite + real PostgreSQL 16.14;
Docker re-checked (absent → boundary recorded, not claimed).
