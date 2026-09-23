# Phase 28 Report

## Status
READY

## Commit
10c979f

## Performance
- evaluation sample: aggregated with explicit sample_count; empty scopes return sample_count 0 with null metrics
- 1X2 metrics: accuracy / log loss / Brier (+ Wilson CI on accuracy, bootstrap CI on Brier)
- goal metrics: home/away/total MAE + RMSE-from-SE
- market metrics: O/U 1.5/2.5/3.5 + BTTS accuracy/log-loss/Brier
- correct-score metrics: exact-score hit rate, predicted top score, actual-score log-prob

## Temporal Analysis
- last 20: trailing window with period + sufficient_sample flag
- last 50: same
- last 100: same
- season-to-date: via season filter
- custom range: date_from/date_to (422 on inverted range)

## Calibration
- bucket methodology: reliability_buckets_v1, deterministic equal-width bins over [0,1], n=10
- ECE: count-weighted, per outcome
- MCE: max bin error, per outcome
- sample size: per outcome + total; empty → null ECE/MCE

## Drift
- current period: trailing window (default 50)
- baseline: full history ≤5000, same filters
- metric differences: absolute + relative per metric
- state: STABLE / WATCH / INSUFFICIENT_DATA (documented rules; no degraded verdict)

## Uncertainty
- methodology: Wilson score interval (z=1.96) for proportions; seeded percentile bootstrap (n=500, seed=7) for scalar means
- sample-size handling: zero trials → null; small samples valid via Wilson; insufficient drift samples flagged

## Data Quality
- readiness: ready/degraded/blocked counts + rates from latest certs per match
- feature completeness: missing required/optional feature tallies from certificates
- provider health: per-provider activation/fixture/result/freshness/failures + identity mapping
- certificate failures: BLOCKED share; duplicate candidates from gate verdicts
- execution failures: ready-but-unpredicted spike rule
- evaluation coverage: finished-predicted outcome gaps

## Coverage
eligible → ready → predicted → completed → evaluated
Counts and rates with denominators; zero denominators yield null (unknown), never zero.

## Provider Monitoring
- provider: per-provider entries + optional provider filter
- competition: filter + per-entry scope
- season: filter + per-entry scope
- activation: actual Phase 24 scoped get_activation_state
- freshness: SourceHealth.updated_at age in hours (48h breach rule)
- coverage: fixture + result counts + result rate
- conflicts: global unresolved count with documented scope note
- failures: failure_count + last_error from source health

## Anomalies
- detected anomalies: 10 deterministic rules (zero generation, coverage collapses, freshness breach, block/cert spikes, execution gaps, impossible metrics, invalid probabilities, duplicate snapshots)
- severity: INFO / WARNING / CRITICAL with minimum-sample guards
- evidence: period, observed/reference values, sample sizes, scope, deterministic IDs; no root-cause claims

## API
- GET /api/v1/monitoring/overview
- GET /api/v1/monitoring/performance
- GET /api/v1/monitoring/calibration
- GET /api/v1/monitoring/drift
- GET /api/v1/monitoring/data-quality
- GET /api/v1/monitoring/coverage
- GET /api/v1/monitoring/providers
- GET /api/v1/monitoring/anomalies
All read-only (verified: no prediction/evaluation/outcome mutation across all endpoints).

## Scheduler
- job: none added (monitoring is purely query-based; documented in PHASE28_MONITORING.md §2)
- locking: n/a
- idempotency: n/a (no writes)

## Frontend
- monitoring views: /monitoring page (performance, coverage funnel, anomalies) + ModelPerformanceSection reuse
- filters: competition, season
- empty states: explicit (no data, no anomalies, insufficient sample)

## Database
- migration: none required (read-only aggregation; head stays 0012_evaluation_records; documented why)
- PostgreSQL version: n/a (no migration)
- upgrade: n/a
- downgrade: n/a
- re-upgrade: n/a
- idempotent rerun: n/a
- schema verification: n/a (no schema change; existing tables untouched)

## Tests
- Phase 28 tests: 46/46 pass
- backend: 807 passed / 1 pre-existing failure / 0 skipped
- frontend: 28/28 pass
- build: tsc && vite build passes
- Ruff: no new debt beyond repo conventions (UP/I001/RUF013/B008/S110/BLE001 shared with baseline)
- golden regression: 0.60605 / 0.22233 / 0.17161, λ 1.7442 / 0.1713 unchanged

## Integrity
- prediction hash: unchanged across all monitoring calls (tested)
- evaluation hash: unchanged (tested)
- outcome hash: unchanged (tested)
- model configuration: unchanged (tested)
- provider activation: unchanged (tested)

## Known Pre-existing Failures
- Phase 18 `test_readiness_splits_not_fixture_only`

## Files Changed
- New: backend/app/services/production_monitoring/ (10 files: __init__, contracts, performance, breakdown, calibration, drift, coverage, data_quality, providers, anomalies), backend/app/api/routes/monitoring.py, backend/tests/test_phase28_monitoring.py, frontend/src/pages/MonitoringPage.tsx, PHASE28_MONITORING.md, PHASE28_REPORT.md
- Modified: backend/app/main.py, frontend/src/api/{client,queries,types}.ts, frontend/src/App.tsx, frontend/src/components/layout/Navbar.tsx, frontend/src/test/apiClient.test.ts

## Final Decision

PHASE 28 READY

## Blocking Issues
NONE
