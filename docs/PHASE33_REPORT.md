# Phase 33 Report — Real-World Performance Validation & Evidence Accumulation

## 1. Phase 33 status
READY (with carried Docker boundary; see §20)

## 2. Commit
470ee37

## 3. Design audit
docs/PHASE33_DESIGN_AUDIT.md: reuse inventory (Phase 2/27 metrics,
Phase 28 uncertainty/calibration, Phase 29 thresholds, Phase 30
identity, Phase 32 pairing), avoided duplication, threshold policy
(20/20/20 convention → MIN_PAIRED_EVIDENCE = 20).

## 4. Evidence architecture
docs/PHASE33_EVIDENCE_ARCHITECTURE.md: observations → eligibility →
cohort → pairs → arm metrics → differences → uncertainty → quality →
state → immutable snapshot. Evidence only, never decisions.

## 5. Evidence states
NO_DATA / INSUFFICIENT_REAL_DATA / DESCRIPTIVE_ONLY / INCONCLUSIVE /
SUPPORTED_DIFFERENCE / CONFLICTING_EVIDENCE / INVALID — deterministic
from counts, CIs, and temporal audit; documented rules in contracts.

## 6. Cohort design
Deterministic fingerprint (artifacts, competitions, seasons, dates,
mode); reuse by hash; ephemeral (non-persisting) cohorts for pure-read
compare endpoints.

## 7. Population definitions
A. champion evals · B. challenger evals · C. paired predictions ·
D. valid paired observations · E. excluded (coded). Comparison uses D.

## 8. Metric implementation
Phase 2/27/28 primitives only: 1X2 acc/logloss/Brier, goal MAEs,
O/U + BTTS, exact-score; paired challenger-minus-champion differences.

## 9. Uncertainty methodology
Seeded percentile bootstrap (7/500/95%) on paired difference series;
Wilson intervals on hit rates; method recorded per result.

## 10. Bootstrap methodology
Resample paired observations as the unit (difference series),
deterministic seed; CIs on Δlogloss/Δbrier drive inferential states.

## 11. Calibration
Recomputed from stored immutable payloads (reliability + ECE + MCE
per arm/outcome); <10 pairs ⇒ INSUFFICIENT_DATA section.

## 12. Temporal validation
cutoff < kickoff per pair; feature-hash equality; outcome-after-cutoff
by FINISHED semantics; counters valid/invalid/post-cutoff/unknown.

## 13. Data-quality validation
Counts, exclusion codes, champion-eval coverage, calibration
availability; poor quality exposed, never hidden.

## 14. API
GET /evidence/{status,cohorts,cohorts/{id},snapshots,snapshots/{id},
compare/{challenger},breakdown/{challenger},uncertainty/{snapshot}}
(read-only, compare writes nothing); POST /evidence/{cohorts,refresh}
(guarded, append-only).

## 15. CLI
`tacticx evidence {status,cohorts,generate,compare,breakdown,show,
refresh}` — service reuse, no business logic in CLI.

## 16. Frontend
`/evidence` route + nav: status, snapshots, paired differences; no
winner/best/rank/promote language. 3 new client tests.

## 17. Database
Migration `0016_evidence` (head, down 0015): `evidence_cohorts` +
`evidence_snapshots`, unique hashes, 8 indexes, no production FKs.

## 18. Tests
- Phase 33: 43/43 pass (26 categories + golden)
- Backend full: 1032 passed / 1 pre-existing (Phase 18) / 0 skipped
- Frontend: 39/39 pass; build passes
- Ruff: no new debt beyond repo conventions

## 19. PostgreSQL evidence
16.14: fresh upgrade → 0016 · downgrade → 0015 (tables removed) ·
re-upgrade → 0016 · idempotent rerun no-op · zero schema drift on both
tables · live cohort→snapshot→rerun on PostgreSQL (DESCRIPTIVE_ONLY,
n=1, deterministic rerun).

## 20. Docker evidence
Docker unavailable on this machine: Compose startup/restart NOT
executed (boundary carried from Phase 31, not claimed).

## 21. Real-data evidence count
0 paired real observations in production (no eligible real fixtures;
test-scoped evidence excluded from production counts).

## 22. Paired observation count
0 in production; deterministic behavior verified on test populations
(1–12 pairs → DESCRIPTIVE_ONLY paths).

## 23. Challenger evaluation count
0 real (same reason).

## 24. Current evidence state
NO_DATA on empty production database (verified via API + CLI).

## 25. No-data behavior
Explicit states, counts, zero synthetic rows, no fake metrics/CIs,
no comparison implied. Tested at service, API, and CLI layers.

## 26. Performance
Single-query loads per table + in-Python aggregation (no full-DB
materialization beyond scoped rows); 5-pair snapshot < 30s budget in
tests; bootstrap 500 resamples deterministic.

## 27. Security
No secrets in new code/migrations/docs; no `.env` tracked; mutations
guarded (403 tested); evidence references ids/hashes, never
credentials or raw provider payloads.

## 28. Regression
Golden `0.60605/0.22233/0.17161`, `λ 1.7442/0.1713` unchanged;
Phase 26 hashes, Phase 27 summaries, Phase 28 overview, Phase 29
baseline, Phase 30 governance all stable (suites green).

## 29. Known limitations
- 0 real paired observations ⇒ production evidence is NO_DATA until
  real fixtures/outcomes accumulate.
- Calibration needs ≥10 pairs; inference needs ≥20.
- Champion-only cohorts are descriptive (INCONCLUSIVE, no comparison).
- Rolled-back artifact re-promotion needs a new candidate version
  (Phase 30 rule, unchanged).

## 30. Existing Phase 18 failure
`test_readiness_splits_not_fixture_only` — pre-existing, unrelated,
untouched.

## 31. Confirmation no model was changed
Golden + integrity guard green; no prediction/model/research files in
diff; champion binding untouched by evidence paths (asserted).

## 32. Confirmation no promotion occurred
No promotion/approval/activation/rollback calls in evidence paths;
registry + event counts asserted unchanged; resolve_active_model_id
stable across refresh.
