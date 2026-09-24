# Phase 30 Model Governance

Contract: `MODEL_GOVERNANCE_V1` · Validator: `governance_validator_v1`

> Research evidence does not itself authorize production activation.

## 1. Architecture

`app/services/model_governance/` (contracts, artifact, registry,
lifecycle, validation, promotion, approval, shadow, deployment, audit,
service) governs authority only. Activation changes the `model_registry`
champion binding; it never edits prediction code, historical snapshots,
evaluations, or default execution paths (those stay pinned to
`ensemble_v1-elo+poisson` — see `docs/PHASE30_DESIGN_AUDIT.md` §6).
Future traffic-switch wiring is explicitly out of scope.

## 2. State machine

```
RESEARCH_ONLY → VALIDATION_PENDING → VALIDATED → CHALLENGER
    → PROMOTION_REQUESTED → APPROVAL_PENDING → APPROVED → SHADOW
    → CANARY_ELIGIBLE → PRODUCTION_ACTIVE
Terminals: REJECTED, WITHDRAWN, ROLLED_BACK, SUPERSEDED, INVALIDATED
Rollback restoration: SUPERSEDED → PRODUCTION_ACTIVE (rollback() only)
```

`transition()` enforces the map; every move appends a
`model_governance_events` row (previous/new state, actor, timestamp,
reason, references). Requesting promotion auto-registers the challenger
role (`VALIDATED → CHALLENGER → PROMOTION_REQUESTED`, two events).

## 3. Data model

`model_artifacts` (hash includes members AND weights — version strings
are weight-blind), `model_registry` (role bindings per scope, ACTIVE /
SUPERSEDED chain), `model_validation_reports` (immutable),
`model_promotion_requests` (OPEN/PENDING/APPROVED/REJECTED — never
self-activating), `model_approval_records` (append-only),
`model_governance_events` (append-only), `shadow_prediction_snapshots`
(isolated outputs). No FKs into production tables.

## 4. Validation process

`validate_candidate()` requires RESEARCH_ONLY state, resolves the linked
Phase 29 experiment (explicit or latest for the candidate), checks
leakage PASS, compatibility (features_v1 + PRE_MATCH + FullPrediction
shape), and evidence state. Results: VALIDATED (measured evidence incl.
neutral), INCONCLUSIVE (missing/insufficient evidence), REJECTED
(incompatible), INVALID (leakage). Neutral evidence validates the
evidence package, not superiority — promotion still needs request +
approval + shadow + canary + activation. Reports are immutable; new
validation = new row.

## 5. Approval process

`decide()` records one explicit decision per call; actor is required
(identities recorded as asserted, never invented).
`required_approval_count` defaults to 1 and is configurable. Meeting the
count moves PROMOTION_REQUESTED → APPROVED; any REJECT closes the
request and the artifact. Partial counts yield APPROVAL_PENDING.

## 6. Shadow process

`start_shadow()` requires APPROVED. `run_shadow_pair()` executes
champion + challenger via the production model classes read-only at a
cutoff and stores both outputs + hashes in `shadow_prediction_snapshots`
only. `evaluate_shadow()` scores pairs with verified outcomes using
Phase 27 definitions and reports factual differences (no winner).

## 7. Production activation

`activate_production()` requires: CANARY_ELIGIBLE state, explicit actor,
`expected_champion_artifact_id` matching the current binding (optimistic
concurrency — stale champions fail safely), and non-identity. Effects:
new ACTIVE champion binding, old binding SUPERSEDED, old artifact
SUPERSEDED, new artifact PRODUCTION_ACTIVE, events appended.

## 8. Rollback

`rollback()` requires explicit actor + target. It binds the target as
ACTIVE, marks the current artifact ROLLED_BACK, and restores a
SUPERSEDED target to PRODUCTION_ACTIVE. History is never rewritten;
historical snapshots keep their recorded model identity.

## 9. Concurrency guarantees

Optimistic concurrency on activation (expected-champion match);
unique constraints on artifact/validation/request/approval/event/shadow
ids and hashes; idempotent artifact registration by hash.

## 10. Failure modes

Stale champion, missing approval, unvalidated/incompatible/rejected
artifacts, insufficient shadow evidence, blocking CRITICAL anomalies,
unknown references, duplicate activation — all fail closed with
machine-readable codes, production binding untouched.

## 11. API

`GET /model-governance/{registry,champion,artifacts/{id},validation/{id},
shadow/{artifact},canary/{artifact},audit,status/{artifact}}` (open) and
guarded mutations: `POST .../{artifacts,validate,challengers,
promotion-requests,approvals,shadow/start,shadow/pair,canary/activate,
production/activate,rollback}` (403 when operational endpoints disabled;
rerun-style confirm not needed — actor + explicit paths suffice).

## 12. Frontend

`/model-governance` page + nav: champion card, challengers,
promotion requests, audit trail. No rankings, no winner language.

## 13. Test evidence

45 Phase 30 tests: unit (identity, transitions), integration (full
lifecycle), adversarial (13 no-auto-promotion cases), 15-step
production-isolation e2e, API incl. guard, migration chain, golden.
See `docs/PHASE30_REPORT.md`.

## 14. Known limitations

- Activation updates governance authority; default execution paths
  remain pinned to ensemble_v1 (traffic-switch wiring is future work).
- Single global scope used in practice; competition/season scoping
  supported by the registry but unexercised against live providers.
- Actor strings are self-asserted (no auth infrastructure exists).
- Re-promotion of rolled-back artifacts requires a new candidate version.
