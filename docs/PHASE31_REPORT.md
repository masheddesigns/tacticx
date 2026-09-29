# Phase 31 Report — Local Continuous Production & Real-Data Acquisition

## 1. Status
READY (with documented runtime-verification limits; see §18)

## 2. Commit
b86936c

## 3. Architecture
Reused full lifecycle (acquire → activation → readiness → prediction →
outcome → evaluation → monitoring) under a new local runtime:
`docker-compose.local.yml` (postgres, redis, migration, api, scheduler
loop, frontend; isolated network; loopback-only ports; persistent
volumes; healthchecks; restart policies). Smallest topology that
provides reliable continuous operation; existing compose files untouched.

## 4. Docker services
tacticx-postgres (16-alpine, pgdata-local), tacticx-redis
(7-alpine appendonly, redisdata-local), migration (one-shot alembic
profile), tacticx-api (`jobs run-due` loop NOT in api; uvicorn),
tacticx-scheduler (`jobs run-due --loop`, 60s stop grace),
tacticx-frontend (nginx). No secrets in file (env_file + substitution).

## 5. Provider status (measured 2026-09-23, not assumed)
- api_football: reachable; EPL 2024 = 380 rows; 2025/2026 = 0 rows →
  2026/27 UNAVAILABLE.
- odds_api: reachable; 1079 soccer_epl market rows (markets only).
- football_data_co_uk: 2627/E0.csv = 50 played, 0 future fixtures.

## 6. Competition/season status
2026/27 in progress (~5 rounds EPL). Results ingestible via CSV;
schedules unavailable from every source → readiness correctly reports
`fixture_count: 0`, `provider_state: UNAVAILABLE`, mode `readiness_only`.

## 7. Acquisition results (soak, scratch SQLite)
Run 1: 50 real 2026/27 EPL matches, 0 rejected, 8.4s. Run 2
(restart simulation): 0 inserted, still 50 rows — idempotent.

## 8. Scheduler results
Loop reuses `run_due()` + locks + terminal records; lock TTL/expiry/
cleanup tested; dry-run idempotent; no new job types.

## 9. Database results
PostgreSQL 16.14 native used for migration verification (head 0014;
fresh upgrade/downgrade/re-upgrade covered by existing chain tests).
Compose persistence via named volumes; restart keeps data by design
(volumes), destructive `down -v` documented as explicit-only.

## 10. Prediction results
ensemble_v1 unchanged; champion binding unchanged; cutoff strictly
enforced; post-cutoff exclusion tested on prod-like flow.

## 11. Outcome results
Real FINISHED/scored ingestion idempotent; conflict-aware scores;
corrections supersede (tested at service layer).

## 12. Evaluation results
Phase 27 path reused on prod-like flow; verified outcomes only;
no config changes from evaluation.

## 13. Monitoring results
Read-only verified (row counts + hashes stable across all monitoring
calls); coverage funnel, data quality, anomalies available via API/CLI.

## 14. Restart tests
Service-layer restart simulation: fixture/status/result re-ingest (no
duplicates), prediction replay (same id), evaluation replay (same id),
lock expiry + reclaim, scheduler re-run. Container-level restart:
spec'd in compose (restart policies, health-gated order); live Docker
restart NOT runnable here (no runtime) — see §18.

## 15. Failure recovery tests
Failure-code unit tests (auth/authz/rate-limit/temporary/schema),
bounded-retry config assertions, Redis memory-fallback, API 503/healthy
separation (providers never affect API health), guard-off 403 covered
by existing suite.

## 16. Backup/restore
Scripts present + executable; `pg_dump` round-trip (schema dump →
gzip → read-back) executed against local PostgreSQL. Full
stop/restore/re-verify cycle documented; live cycle requires Docker.

## 17. Security audit
No `.env` tracked; only `*.example`; no secrets in git history; no
secret literals in new files/compose/docs; diagnose() presence-only;
existing security checks untouched.

## 18. Real-data soak-test period
2026-09-23, three live probes (api_football ×4 calls, odds_api ×1,
CSV ×3 fetches + 2 import runs), all within rate limits, total <60s
provider time. No continuous multi-day soak possible in this session;
scheduler loop + intervals are configured for it.

## 19. Real records acquired
50 real 2026/27 EPL finished matches (+ teams/stats via pipeline).

## 20. Real predictions generated
0 (honest): no upcoming 2026/27 fixtures exist at any source, so no
real pre-match prediction is possible. Synthetic fixtures were NOT
created.

## 21. Real outcomes evaluated
0 new (no real predictions exist to evaluate). Historical-outcome
evaluation path covered by existing suites.

## 22. Known limitations
- No Docker runtime on this machine: `docker compose` startup/restart/
  live soak NOT executed here; compose validated statically (YAML +
  contract tests). Must run where Docker exists before claiming
  end-to-end runtime validation.
- No continuous multi-day soak in-session.
- 2026/27 schedules unavailable everywhere measured → real upcoming
  predictions blocked by data, not by software.
- Celery worker/beat intentionally out of scope (scheduler loop used).

## 23. Known failures
- Phase 18 `test_readiness_splits_not_fixture_only` (pre-existing, untouched).

## 24. Existing Phase 18 failure classification
Pre-existing, unrelated to Phase 31 (readiness-split reporting in
current-season acquisition; Phase 31 adds no acquisition logic).

## 25. Confirmation that ensemble_v1 was not modified
Golden values pass; integrity guard passes; champion binding resolves
`ensemble_v1-elo+poisson`; no model files touched (`git status` shows
none).

## 26. Confirmation that Phase 30 governance was not bypassed
No governance writes in Phase 31 code paths; registry untouched;
no promotion/approval/activation calls outside governance tests.

## 27. Confirmation that no automatic promotion exists
No new selection logic; scheduler loop only runs existing jobs;
research candidates unreachable from the loop.
