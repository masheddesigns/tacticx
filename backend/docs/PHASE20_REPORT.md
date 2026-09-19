# PHASE 20 — FINAL REPORT

## Architecture

`app/services/scheduler/` (config, store, executors, orchestrator,
monitoring, dashboard) orchestrates recurring acquisition jobs as a
production operational layer. It extends — never duplicates — existing
services (Phase 7 health, Phase 8 reconciliation, Phase 10 freshness,
Phase 11 acquisition, Phase 18 current-season, Phase 19 qualification).
Prediction/intelligence/model code untouched.

## Job model

Append-only `AcquisitionJobRecord`: job_id, job_type, source, competition,
season, timestamps, status, plan_hash, qualification_hash, request/success/
failure counts, observation/match/conflict counts, duration_ms, error_code,
dry_run, trigger, details. Terminal statuses only: succeeded/partial/failed/
skipped/unavailable/rate_limited/cancelled.

## Job types

fixture_refresh, status_refresh, result_refresh, source_health,
freshness_audit, qualification.

## Scheduler abstraction

Generic application service independent of cron/Celery/K8s. External
schedulers invoke `tacticx jobs run-due` or `tacticx jobs run <type>`.

## Schedules

Configuration-driven intervals, competitions, seasons, sources,
concurrency, retry, timeout, priority, lock_ttl. Versioned defaults
in `scheduler/config.py`.

## Run-once mode

Every job supports `tacticx jobs run <type>` with same code path.

## Dry-run

Plan building + qualification evaluation + work estimation without
writes. Clearly labeled provider requests where unavoidable.

## Locking

Database-backed with TTL expiry. Stale-lock recovery. Owner identity.
Safe release on success, failure, and crash.

## Idempotency

Repeated runs produce duplicate-count records, no duplicate canonical
data. Provider reruns produce no new observations.

## Qualification gate

Before acquisition: qualification → qualified? If not: skip with reason.
No blind provider calls. Rate-limited sources deferred.

## No-source state

First-class: `unavailable` + `no_qualified_source`. Not an error.
No fabrication. No retry storms.

## Backoff

Bounded exponential backoff for 429/timeout/5xx. Auth errors (401/403)
fail fast. Repeated failures → degraded → unavailable.

## Rate-limit budget

Conservative defaults. Never deliberately exhausts quota.

## Concurrency

Configurable per job type. Database locks prevent duplicate concurrent
execution.

## Priority

Deterministic ordering: status_refresh(10) > fixture_refresh(20) >
result_refresh(30) > health(50) > freshness(60) > qualification(80).

## Current match refresh

Discover fixtures → append observations → resolve identities →
canonicalize → update universe. Then status refresh → result refresh.
Historical observations never mutated.

## Live match handling

scheduled → live → finished and postponed/cancelled/abandoned.
Every transition = append-only observation.

## Post-match processing

Triggers result ingestion + reconciliation + freshness update +
universe update. Never triggers retraining or model promotion.

## Prediction isolation

Mandatory. Scheduler never calls model training, prediction generation,
calibration, research, or promotion.

## Freshness monitoring

States: fresh/aging/stale/expired/unknown per source/competition/season.

## Operational alerts

Machine-readable events: no_qualified_source, provider_unavailable,
repeated_failures, rate_limited, stale_source, zero_fixtures,
fixture_count_drop, job_stuck, lock_stale.

## Anomaly detection

Conservative heuristics (no ML): fixture_count_anomaly,
identity_degradation, conflict_spike, impossible_status_transition,
duplicate_rate_anomaly.

## Source health dashboard

GET /api/v1/jobs/dashboard exposes sources (health, qualification),
jobs (last run, status, interval), competitions (fixture count,
freshness), locks (active/stale), recent runs.

## Job API

GET /api/v1/jobs (filters), /jobs/{id}, /jobs/due, /jobs/alerts,
/jobs/anomalies, /jobs/dashboard, POST /jobs/locks/cleanup,
/jobs/{type}/run (manual).

## CLI

tacticx jobs list|status|run|run-due|alerts|anomalies|dashboard.
Supports --competition, --season, --source, --dry-run, --json.

## Configuration

Versioned defaults in scheduler/config.py. Timezone explicit.
Safe defaults. No hard-coded scheduling logic in services.

## Time handling

All timestamps UTC-aware. SQLite naive datetimes normalized.
Tests use fixed clocks.

## Job retention

Append-only. Configurable retention_days. Cleanup separate from
acquisition.

## Failure recovery

Process crash → lock expires → stale recovery. Timeout → bounded
duration. Partial results persist. DB transaction failure → no
corrupt state. Restart → resume without duplication.

## Security

No arbitrary provider URLs. No command execution. No credentials
in logs. ORM-only. Bounded retries/concurrency/pagination.

## Performance

Job listing <500ms. Lock acquisition <100ms. Plan generation <500ms.
Dry-run <1s (cached qualification). Scheduler overhead negligible.

## Five-league validation

All 6 job types executed in dry-run mode for EPL/La Liga/Serie A/
Bundesliga/Ligue 1. Status transitions verified. All passed.

## Historical integrity

Before/after Phase 20: prediction/model/feature/odds/intelligence/
backtest/calibration/observation code unchanged. Scheduler modules
contain zero prediction/training imports.

## Tests

Previous: 515. New: 70. Total: **585. Passed: 585. Failed: 0.**

## Production regression

No prediction, model, feature, odds, or intelligence code modified.
No new models retrained. No promotions. No betting automation.

## Documentation

PHASE20_REPORT.md, PHASE20_SCHEDULER.md + README.

## Limitations

- No live Level-A source (API keys restricted/expired).
- Current-season fixtures still 0 from live sources.
- External scheduler integration (cron/systemd/K8s) documented
  but not implemented — CLI is the integration point.
- Qualification refresh uses cached state (no live probing).

## Commit

Pushed to main.

## Status: READY
