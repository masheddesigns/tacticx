# Phase 20 — Production Acquisition Scheduler

## Architecture

```
Scheduler (config-driven, run_due / run_job)
    ↓
Job Planner (due calculation, priority ordering)
    ↓
Lock Acquisition (database-backed, TTL expiry, stale recovery)
    ↓
Job Record (append-only)
    ↓
Provider Qualification Gate
    ↓
Executor (one per job type)
    ↓
Existing Services (acquisition, health, freshness, qualification)
    ↓
Operational Result (recorded, never mutating predictions)
```

## Job types

| Job | Priority | Default interval | Purpose |
|-----|----------|-----------------|---------|
| status_refresh | 10 | 30 min | Match status transitions |
| fixture_refresh | 20 | 6 h | Upcoming fixture discovery |
| result_refresh | 30 | 6 h | Completed result discovery |
| source_health | 50 | 4 h | Provider health telemetry |
| freshness_audit | 60 | 6 h | Data staleness assessment |
| qualification | 80 | 7 days | Provider qualification refresh |

## Locking

Database-backed with TTL expiry. Stale locks are reclaimed on
acquisition. Safe after process failure — no manual intervention needed.

## Dry-run

`--dry-run` builds the plan, evaluates qualification, estimates work,
and reports expected requests without writing observations or consuming
provider quota.

## Prediction isolation

The scheduler never triggers model training, prediction generation,
calibration fitting, research experiments, or model promotion. The only
relationship is: acquisition → data readiness → prediction MAY later
consume it.
