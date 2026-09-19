"""Scheduler configuration — versioned, safe defaults, no hard-coded schedules.

Configuration drives the scheduler; scheduling logic is never hard-coded
inside services. Each job type supports: enabled, interval_seconds,
competitions, seasons, sources, max_concurrency, retry_policy (max,
base_seconds), timeout_seconds, priority, lock_ttl_seconds.
"""
from __future__ import annotations

import copy
from typing import Any

# Job type constants — canonical names used everywhere.
JOB_FIXTURE_REFRESH = "fixture_refresh"
JOB_STATUS_REFRESH = "status_refresh"
JOB_RESULT_REFRESH = "result_refresh"
JOB_HEALTH_CHECK = "source_health"
JOB_FRESHNESS_AUDIT = "freshness_audit"
JOB_QUALIFICATION = "qualification"

ALL_JOB_TYPES = (
    JOB_FIXTURE_REFRESH,
    JOB_STATUS_REFRESH,
    JOB_RESULT_REFRESH,
    JOB_HEALTH_CHECK,
    JOB_FRESHNESS_AUDIT,
    JOB_QUALIFICATION,
)

# Priority ordering: lower number = higher priority.
DEFAULT_PRIORITIES = {
    JOB_STATUS_REFRESH: 10,
    JOB_FIXTURE_REFRESH: 20,
    JOB_RESULT_REFRESH: 30,
    JOB_HEALTH_CHECK: 50,
    JOB_FRESHNESS_AUDIT: 60,
    JOB_QUALIFICATION: 80,
}

DEFAULT_SCHEDULER: dict[str, Any] = {
    "enabled": True,
    "timezone": "UTC",
    "max_concurrency": 3,
    "lock_ttl_seconds": 300,
    "default_retry_max": 2,
    "default_retry_base_seconds": 30.0,
    "default_timeout_seconds": 120.0,
    "retention_days": 90,
}

DEFAULT_JOBS: dict[str, dict[str, Any]] = {
    JOB_FIXTURE_REFRESH: {
        "enabled": True,
        "interval_seconds": 6 * 3600,
        "competitions": ["EPL", "LA_LIGA", "SERIE_A", "BUNDESLIGA", "LIGUE_1"],
        "seasons": ["current"],
        "sources": [],
        "max_concurrency": 1,
        "retry_max": 2,
        "retry_base_seconds": 30.0,
        "timeout_seconds": 120.0,
        "priority": DEFAULT_PRIORITIES[JOB_FIXTURE_REFRESH],
        "lock_ttl_seconds": 300,
    },
    JOB_STATUS_REFRESH: {
        "enabled": True,
        "interval_seconds": 30 * 60,
        "competitions": ["EPL", "LA_LIGA", "SERIE_A", "BUNDESLIGA", "LIGUE_1"],
        "seasons": ["current"],
        "sources": [],
        "max_concurrency": 1,
        "retry_max": 3,
        "retry_base_seconds": 15.0,
        "timeout_seconds": 90.0,
        "priority": DEFAULT_PRIORITIES[JOB_STATUS_REFRESH],
        "lock_ttl_seconds": 120,
    },
    JOB_RESULT_REFRESH: {
        "enabled": True,
        "interval_seconds": 6 * 3600,
        "competitions": ["EPL", "LA_LIGA", "SERIE_A", "BUNDESLIGA", "LIGUE_1"],
        "seasons": ["current"],
        "sources": [],
        "max_concurrency": 1,
        "retry_max": 2,
        "retry_base_seconds": 30.0,
        "timeout_seconds": 120.0,
        "priority": DEFAULT_PRIORITIES[JOB_RESULT_REFRESH],
        "lock_ttl_seconds": 300,
    },
    JOB_HEALTH_CHECK: {
        "enabled": True,
        "interval_seconds": 4 * 3600,
        "competitions": [],
        "seasons": [],
        "sources": ["api_football", "odds_api", "football_data_co_uk"],
        "max_concurrency": 1,
        "retry_max": 1,
        "retry_base_seconds": 5.0,
        "timeout_seconds": 30.0,
        "priority": DEFAULT_PRIORITIES[JOB_HEALTH_CHECK],
        "lock_ttl_seconds": 60,
    },
    JOB_FRESHNESS_AUDIT: {
        "enabled": True,
        "interval_seconds": 6 * 3600,
        "competitions": ["EPL", "LA_LIGA", "SERIE_A", "BUNDESLIGA", "LIGUE_1"],
        "seasons": ["current"],
        "sources": [],
        "max_concurrency": 1,
        "retry_max": 1,
        "retry_base_seconds": 5.0,
        "timeout_seconds": 60.0,
        "priority": DEFAULT_PRIORITIES[JOB_FRESHNESS_AUDIT],
        "lock_ttl_seconds": 120,
    },
    JOB_QUALIFICATION: {
        "enabled": True,
        "interval_seconds": 7 * 24 * 3600,
        "competitions": ["EPL", "LA_LIGA", "SERIE_A", "BUNDESLIGA", "LIGUE_1"],
        "seasons": ["current"],
        "sources": ["api_football", "odds_api"],
        "max_concurrency": 1,
        "retry_max": 1,
        "retry_base_seconds": 10.0,
        "timeout_seconds": 30.0,
        "priority": DEFAULT_PRIORITIES[JOB_QUALIFICATION],
        "lock_ttl_seconds": 60,
    },
}


def get_scheduler_config() -> dict[str, Any]:
    """Return a deep copy of the default scheduler configuration."""
    return copy.deepcopy(DEFAULT_SCHEDULER)


def get_job_config(job_type: str) -> dict[str, Any]:
    """Return a deep copy of the config for one job type."""
    if job_type not in DEFAULT_JOBS:
        raise ValueError(f"unknown job type: {job_type!r}")
    return copy.deepcopy(DEFAULT_JOBS[job_type])


def get_all_job_configs() -> dict[str, dict[str, Any]]:
    """Return deep copies of all job configurations."""
    return {jt: get_job_config(jt) for jt in ALL_JOB_TYPES}


def lock_key(job_type: str, competition: str = "") -> str:
    """Deterministic lock key: same (job_type, competition) → same key."""
    parts = [job_type]
    if competition:
        parts.append(competition)
    return "|".join(parts)
