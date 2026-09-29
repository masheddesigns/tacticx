# Phase 31 Design Audit — Local Continuous Production

**Date**: 2026-09-23 · **Baseline**: `8183e03` (Phase 30 CLOSED/READY) ·
Branch `main`, clean tree. Alembic head: `0014_model_governance`.

## 1. Can the application run entirely locally?

Mostly, with three gaps:

1. **No continuous scheduler loop.** Jobs run only via manual CLI
   (`tacticx jobs run/run-due`) or guarded HTTP. `interval_seconds` is
   declarative (`store.is_due`); no daemon, APScheduler, or beat service
   exists in either compose file (Celery `beat_schedule` is defined but
   no beat container runs it). → Phase 31 adds a minimal `jobs run-due
   --loop` process reusing `run_due()` + locks + idempotency.
2. **Dev compose has no frontend/healthcheck/restart**; prod compose has
   no worker and requires manual `run --rm migration`. → Phase 31 adds
   `docker-compose.local.yml` (prod-like, local-safe) without touching
   existing files.
3. **No container runtime on this machine** (no docker/colima/podman).
   Compose artifacts are validated statically (YAML parse + contract
   tests); live `docker compose` verification is BLOCKED here and must
   run where Docker exists. PostgreSQL 16.14 runs natively and is used
   for all database verification.

## 2. Missing components for continuous operation

- Scheduler loop process (new, thin wrapper over `run_due()`).
- Local-prod compose topology (new file).
- `.env.example` additions for new settings (no secrets).
- CLI status commands: `system status`, `providers status`,
  `prediction status`, `evaluation status`, `monitoring summary`,
  `acquisition status` (thin wrappers over existing services).
- Config flags: `TACTICX_ENV`, `SCHEDULER_ENABLED`,
  `PREDICTION_ENABLED`, `EVALUATION_ENABLED` (safe defaults).
- Additive `migrations` key on `/ready` (non-fatal, schema-preserving).

## 3. Reusable scheduler functionality

All of it: `run_job`/`run_due`/`run_job_manual`, DB locks with TTL +
stale reclamation, `is_due`/`find_due_jobs`, terminal records,
`check_alerts`/`detect_anomalies`, per-job retry/timeout/lock config.
Eight job types already cover the full lifecycle; no new job types.

## 4-7. Provider reality (measured, not assumed)

| Provider | Key | Qualification | 2026/27 |
|---|---|---|---|
| api_football | `FOOTBALL_API_KEY` | REJECTED (403 on /fixtures) | UNAVAILABLE |
| odds_api | `ODDS_API_KEY` | REJECTED fixtures (401); Level-C markets only | UNAVAILABLE |
| football_data_co_uk | none (bulk CSV) | Level-A (historical bulk) | UNAVAILABLE (historical seasons only) |

Failure codes in use (lowercase, bounded retries, auth fail-fast):
`authentication_failure`, `authorization_failure`, `rate_limited`,
`temporary_failure`, `provider_schema_error`, `validation_failure`,
`provider_empty`, `provider_5xx`, `provider_timeout`,
`provider_malformed`. State machine
UNAVAILABLE→…→QUALIFIED→ACTIVE (+DEGRADED/REVOKED) with the
QUALIFIED≠ACTIVE invariant; only ACTIVE triggers acquisition.

## 8. Disabled acquisition paths

`execute_result_refresh` is observation-only (counts, no Pipeline
ingest). Celery beat never runs. `POST /jobs/*/run` is prod-disabled by
default (operational guard). Phase 31 does not change these; the loop
uses the same paths as manual invocation.

## 9. Manual-only operations today

All scheduler jobs, qualification probes, readiness persist, prediction
execution (outside tests), evaluation runs. The loop + new CLI status
commands close the operability gap without duplicating service logic.

## 10-12. Restart safety (by construction, verified by tests)

- Fixtures: `MatchResolver.ensure` + `uq_match_provider` → same
  canonical row; re-acquisition updates, never duplicates.
- Statuses/results: conflict-aware `check_score`, never blind overwrite.
- Predictions: `execution_key` UNIQUE → replay returns existing row.
- Evaluations: `evaluation_key` UNIQUE → replay returns existing row.
- Outcomes: `(match_id, outcome_hash)` UNIQUE → corrections supersede.
- Locks: TTL expiry + `cleanup_expired_locks`; interrupted jobs retry
  safely. New Phase 31 tests prove each property with stop/restart
  simulation at the service layer.

## 13. Redis role (unchanged)

Cache + Celery broker + health probe only; rate limiting in-memory;
locks in Postgres; authoritative state always Postgres. Redis restart =
memory fallback, `ready=degraded`, full recovery. No Redis changes.

## 14. Secrets

`.env` gitignored; only `*.example` tracked; no secrets in git history;
prod compose `SECRET_KEY` fallback documented as must-override.
Phase 31 adds no secrets; security audit re-verifies.
