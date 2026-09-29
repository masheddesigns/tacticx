# Phase 34 Report — Controlled Candidate Validation & Production-Change Gate

## 1. Status
READY (with carried Docker boundary; see §21)

## 2. Commit
(to be filled after commit)

## 3. Design audit
docs/PHASE34_DESIGN_AUDIT.md: reuse inventory, threshold rationale,
authority boundary (writes reports only). Includes the previously
uncommitted Phase 32 chain-ownership test edit, committed here.

## 4. Validation architecture
docs/PHASE34_VALIDATION_ARCHITECTURE.md: evidence → 14 rules → state →
immutable report → human Phase 30 review. No governance writes.

## 5. Validation configuration
`candidate_validation_v1` (v1): 50 pairs, 30% exclusion cap, 0 temporal
violations, SUPPORTED/INCONCLUSIVE evidence allowed, calibration
required, rationale recorded. Unknown ids fail closed.

## 6. Rule engine
14 deterministic rules (identity, sufficiency, temporal, outcome,
shared-input, schema, artifact hash, provenance, snapshot integrity,
calibration, stability, compatibility, operational health, rollback
target), each with state/explanation/measured/required/reference.

## 7. Evidence binding
Candidate + champion + snapshot + config pinned per report; snapshot
hash re-verified at read; mismatch/corruption → BLOCKED/INVALID paths.

## 8. Statistical validation
Phase 33 paired bootstrap CIs + Wilson intervals consumed as-recorded;
gate checks thresholds/states, never reinterprets or invents methods.

## 9. Temporal validation
Phase 33 eligibility results consumed; violation rate > 0 blocks;
post-cutoff contamination cannot enter (excluded upstream).

## 10. Compatibility
Phase 30 `check_compatibility` reused (schema, normalization, goals,
mode); incompatible output → rejection, never coercion.

## 11. Reproducibility
Seed/dataset/code/protocol persisted on evidence; validation hash
covers all inputs; reruns byte-identical (tested).

## 12. Operational health
CRITICAL anomalies (Phase 28 read) block; others observed; provider
outages classified as conditions, never performance claims.

## 13. Staleness/concurrency
VALID/STALE/SUPERSEDED via champion comparison + newer-report check;
stale validations must not be used for handoff (tested both paths).

## 14. Governance handoff
VALIDATED_FOR_GOVERNANCE reports reference for later human Phase 30
use. Zero promotion/approval/activation/rollback calls in Phase 34
code paths (asserted: counts unchanged; source has no such imports).

## 15. API
GET /candidate-validation/{status,config,configs,candidates,
{id},/{id}/rules,/{id}/evidence,/{id}/staleness} +
POST /candidate-validation/{run,refresh} (guarded, 403 tested).

## 16. CLI
`tacticx validation {status,config,candidates,run,show,rules,refresh}`
— service reuse, explicit args, no business logic in CLI.

## 17. Frontend
`/validation` route + nav: champion, candidates, rule list with states,
metrics, data quality; never Approved/Production/Best/Winner. 3 new
client tests.

## 18. Database
Migration `0017_candidate_validation` (head, down 0016):
`candidate_validation_reports` (21 cols, 7 indexes, no production FKs).

## 19. Tests
- Phase 34: 44/44 pass (28 categories + golden)
- Backend full: 1076 passed / 1 pre-existing (Phase 18) / 0 skipped
- Frontend: 42/42 pass; build passes
- Ruff: no new debt beyond repo conventions

## 20. PostgreSQL evidence
16.14: fresh upgrade → 0017 · downgrade → 0016 (table removed) ·
re-upgrade → 0017 · idempotent rerun no-op · zero drift · live
cohort→snapshot→validation→rerun→staleness on PostgreSQL
(INSUFFICIENT_DATA on empty evidence, deterministic, VALID).

## 21. Docker evidence
Docker unavailable on this machine: runtime NOT executed (boundary
carried from Phase 31, not claimed).

## 22. Real-data validation state
INSUFFICIENT_DATA (0 real paired observations) — the correct,
tested current-state result.

## 23. Validation count
0 production validations (no eligible real evidence); test-scoped
validations excluded from production counts.

## 24. Current champion
ensemble_v1-elo+poisson (resolved before/after every validation run).

## 25. Candidate state
No production candidates (test artifacts only, isolated DBs).

## 26. Security
No secrets in new code/migrations/docs; no `.env` tracked; mutations
guarded; reports carry ids/hashes, never credentials or raw provider
payloads.

## 27. Regression
Golden `0.60605/0.22233/0.17161`, `λ 1.7442/0.1713` unchanged;
Phase 26/27/28/29/30/32/33 suites green (except pre-existing Phase 18).

## 28. Known limitations
- 0 real pairs ⇒ only INSUFFICIENT_DATA reachable in production today.
- Thresholds conservative by design; require human sign-off to relax.
- Actors self-asserted (no auth infrastructure).
- No scheduler integration (manual invocation preferred; documented).

## 29. Existing Phase 18 failure
`test_readiness_splits_not_fixture_only` — pre-existing, unrelated,
untouched.

## 30. Confirmation no production model was changed
Golden + integrity green; champion binding asserted stable; no model
files in diff.

## 31. Confirmation no automatic promotion occurred
Zero promotion/approval/activation/rollback writes across all runs;
registry + event counts asserted unchanged; validation package has no
such imports.
