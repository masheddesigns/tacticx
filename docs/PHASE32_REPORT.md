# Phase 32 Report — Real-Data Champion/Challenger Shadow

## 1. Status
READY (with carried Docker/soak boundary; see §19)

## 2. Commit
b30b205

## 3. Existing Phase 30 functionality reused
`ShadowPredictionSnapshot` table, `start_shadow` (approval gate),
`run_shadow_pair` (isolated execution, untouched), `evaluate_shadow`
(factual scoring), artifact registry, lifecycle machine, validation,
promotion requests, counted approvals, canary checklist, activation,
rollback, audit trail. No second governance system built.

## 4. Challenger artifact
Phase 29 `elo_only` builtin bridged via `register_candidate_artifact`
(model_id `elo_v1`, weights in config fingerprint); SHADOW state via
the standard validate → request → approve → start flow. Labeled
research challenger; never production-ready by construction.

## 5. Shared feature architecture
Shadow execution resolves the champion's stored Phase 26
`PredictionFeatureSnapshot` row and binds its id + hash into the
shadow row; the challenger reads (never rebuilds) that input.
`validate_shadow_pair` enforces match/kickoff/cutoff/mode + hash
equality + champion-prediction binding.

## 6. Temporal validation
Cert cutoff < kickoff enforced; champion-prediction ↔ latest-cert
cutoff correspondence enforced (new-cutoff-mismatch refuses);
post-cutoff odds/results/events/lineups provably excluded (adversarial).

## 7. Shadow execution
`execute_shadow()` (service/API/CLI/scheduler): eligibility gates →
shared snapshot → research-path challenger run → Phase 26 validation +
Phase 30 compatibility → immutable row. Failures fail closed with
codes; champion path byte-identical afterwards.

## 8. Shadow storage
Extended `shadow_prediction_snapshots` (additive columns only) +
`shadow_evaluation_records`; UNIQUE execution/evaluation keys;
idempotent reruns; no production-table writes.

## 9. Pairing
The shadow row is the explicit pair (match, both artifacts, shared
snapshot, cutoff, timestamps); `pairs/{id}/validate` verifies it.
No timestamp-inferred pairing.

## 10. Outcome linkage
Shared Phase 27 `capture_outcome_snapshot` identity for both arms;
corrections supersede per Phase 27; re-evaluation versions explicitly.

## 11. Evaluation
Champion via existing `evaluate_prediction_snapshot`; challenger via
identical `score_snapshot` persisted to shadow records. Metrics:
1X2/logloss/Brier/goals/markets/scores + differences + sample notes.

## 12. Monitoring
Read-only `shadow_summary` (coverage, per-challenger counts) and
`shadow_comparison` (aggregate diffs, INSUFFICIENT_DATA < 20). No
governance triggers; production monitoring untouched.

## 13. API
`GET /shadow/{summary,challengers,matches,matches/{id},evaluations,
comparison/{id},pairs/{id}/validate}` (open) +
`POST /shadow/{execute/{id},start,pairs/{id}/evaluate}` (guarded, 403
tested). No activation/promotion surface.

## 14. CLI
`tacticx shadow {status,challengers,matches,evaluate,compare,run,
audit}` — service reuse, no business logic in CLI.

## 15. Frontend
`/shadow` route + nav: status cards, challenger select, factual
comparison table (no winner language). 3 new client tests.

## 16. Database migration
`0015_shadow_execution` (head, down 0014): 4 additive columns +
3 indexes + `shadow_evaluation_records` (13 cols, 7 indexes).

## 17. Tests
- Phase 32: 64/64 pass (21 categories + golden + migration)
- Backend full: 988 passed / 1 pre-existing (Phase 18) / 0 skipped
- Frontend: 36/36 pass; build passes
- Ruff: no new debt beyond repo conventions

## 18. PostgreSQL evidence
16.14: fresh upgrade → 0015 (4 columns + eval table, counts verified);
downgrade → 0014 (columns/table removed); re-upgrade → 0015;
idempotent rerun no-op. Live full chain on PostgreSQL: cert →
champion pred → governance flow → shadow (shared snapshot id match) →
pair valid → shared-outcome evaluation → champion unchanged.

## 19. Docker evidence
Docker remains unavailable on this machine: Compose startup/restart
NOT executed (boundary carried from Phase 31, not claimed).

## 20. Real-data soak results
Eligible real fixtures: 0 (no upcoming 2026/27 at measured sources) →
`NO_ELIGIBLE_MATCHES` honestly reported by scan, API, CLI, scheduler
dry-run. No synthetic production records created.

## 21. Number of real shadow predictions
0 (correct: no eligible real fixtures; test-only executions excluded).

## 22. Number of real challenger evaluations
0 (same reason; shared-outcome mechanism proven on PostgreSQL with
test-scoped data).

## 23. Number of real outcomes evaluated
0 new real outcomes (no real predictions exist to evaluate).

## 24. Failure/recovery results
18 failure modes tested (missing/invalid challenger, incompatible/NaN
output, missing feature row, cutoff mismatch, blocked/stale matches,
duplicates, unknown match, executor errors); restart tests pass
(same row/record on re-execution); champion intact after every failure.

## 25. Security results
No secrets in new code/migrations/docs/compose; no `.env` tracked;
shadow APIs guarded (403 tested); challenger metadata carries no
credentials (config fingerprints only).

## 26. Known limitations
- 0 eligible real fixtures ⇒ production-like shadow idle (valid).
- Default execution paths stay pinned to ensemble_v1 (Phase 30 design).
- Registry competition/season scoping supported, exercised globally.
- Scheduler needs `challenger_artifact_id` configured, else skips.

## 27. Existing Phase 18 failure
`test_readiness_splits_not_fixture_only` — pre-existing, unrelated,
untouched.

## 28. Confirmation ensemble_v1 remains champion
`resolve_active_model_id()` returns `ensemble_v1-elo+poisson` after all
shadow/evaluation/scheduler operations (asserted in tests + live PG run).

## 29. Confirmation production predictions were not modified
Row-count + hash assertions across shadow/evaluate/scheduler/API
operations; historical hashes byte-identical.

## 30. Confirmation no automatic promotion exists
No metric/scheduler/monitoring/research trigger promotes; adversarial
tests (better-metrics, anomalies, repeated scheduler runs) assert
registry + request counts unchanged; source inspection clean.
