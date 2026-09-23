# Phase 29 Report

## Status
READY

## Commit
fbeef83

## Research Architecture
- isolated `app/services/research/` (contracts/datasets/candidates/experiments/isolation)
- production services untouched; integrity guard passes

## Production Isolation
- locked files + config fingerprinted before/after runs: intact
- no production snapshot/evaluation/monitoring/provider/scheduler writes (tested)
- no PRODUCTION status in lifecycle

## Dataset
- versioned, hashed, provenance-bearing; kickoff_minus_24h cutoffs
- chronological train/validation/test thirds with recorded boundaries
- temporal audit PASS; deterministic rebuild reuse

## Baseline Reproduction
- baseline_repro identical to production path (Δlogloss = Δbrier = 0.0)
- golden values unchanged

## Candidates
- baseline_repro, poisson_only, elo_only, ensemble_weighted_60_40
- poisson_only shows REGRESSION_EVIDENCE on smoke data (framework discriminates)

## Experiments
- candidate × dataset × protocol runner with idempotent rerun
- invalid experiments recorded auditable on leakage

## Evaluation
- 1X2 / goals / markets / correct-score via Phase 2 + Phase 27 definitions
- calibration ECE per outcome; sample sizes everywhere

## Comparison
- deterministic paired bootstrap CIs; neutral evidence states; documented rules

## Uncertainty
- paired bootstrap (seed 7, n_boot 2000); insufficient-data state below n=20

## Leakage Protection
- cutoff/kickoff + chronological audit; declared-input allowlist
- 5 adversarial rejections tested (future results, live odds, target leak, unsupported family, cross-dataset mixing impossible by hash binding)

## Reproducibility
- rerun returns identical result_hash; seed/dataset/code/protocol persisted

## Multiple-Comparison Protection
- family_experiment_count + selection note per result; registry queryable; no auto-promotion

## API
- POST/GET /research/candidates (+builtin), /research/datasets (+detail audit), /research/experiments (+detail/comparison/run with guard+confirm)
- execution requires operational_endpoints_enabled; rerun requires confirm=true

## Frontend
- /research page: candidates, datasets, experiments, neutral comparison, reproducibility, leakage
- nav entry; 3 new client tests

## Database
- migration 0013_research_registry (head, down 0012)
- PostgreSQL 16.14: fresh upgrade / downgrade / re-upgrade / idempotent rerun PASS
- live research run + rerun determinism PASS on PostgreSQL

## Tests
- Phase 29: 38/38 pass
- backend: 845 passed / 1 pre-existing failure / 0 skipped
- frontend: 31/31 pass
- build: tsc && vite build passes
- Ruff: no new debt beyond repo conventions
- golden regression: unchanged

## Production Integrity
- model: intact (file hashes)
- configuration: intact
- prediction snapshots: unchanged counts
- evaluations: unchanged counts
- monitoring: unaffected
- provider activation: unchanged
- scheduler: ALL_JOB_TYPES unchanged (8)

## Known Pre-existing Failures
- Phase 18 `test_readiness_splits_not_fixture_only`

## Files Changed
- New: backend/app/services/research/ (6 files), backend/app/db/models/research_registry.py, backend/app/api/routes/research.py, backend/migrations/versions/0013_research_registry.py, backend/tests/test_phase29_research.py, frontend/src/pages/ResearchPage.tsx, PHASE29_RESEARCH.md, PHASE29_REPORT.md
- Modified: backend/app/db/models/__init__.py, backend/app/main.py, backend/tests/test_phase27_evaluation.py (chain assertion, not head), frontend/src/api/{client,queries,types}.ts, frontend/src/App.tsx, frontend/src/components/layout/Navbar.tsx, frontend/src/test/apiClient.test.ts

## Final Decision

PHASE 29 READY

## Blocking Issues
NONE
