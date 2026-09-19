"""Scheduler dashboard — aggregated operational data for API/CLI.

Extends acquisition status with scheduler-specific metrics: job history,
source health/qualification/freshness, competition fixture counts, and
operational readiness. No secrets, no raw payloads.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.db.models.core import League, Match
from app.db.models.lifecycle import SourceHealth
from app.db.models.scheduler import AcquisitionJobLock, AcquisitionJobRecord
from app.services.provider_qualification import registry as reg_mod
from app.services.scheduler.config import ALL_JOB_TYPES, get_job_config


def _now() -> datetime:
    return datetime.now(timezone.utc)


def scheduler_status(db: Session) -> dict[str, Any]:
    """Full scheduler dashboard data."""
    return {
        "as_of": _now().isoformat(),
        "sources": _source_summaries(db),
        "jobs": _job_summaries(db),
        "competitions": _competition_summaries(db),
        "locks": _lock_summary(db),
        "recent_runs": _recent_runs(db),
    }


def _source_summaries(db: Session) -> dict[str, Any]:
    """Per-source: health, qualification, freshness, last success/failure."""
    reg = reg_mod.get_registry()
    out = {}
    for entry in reg.ordered(enabled_only=True):
        source = entry.source_id
        health_row = db.query(SourceHealth).filter_by(source=source).first()
        health_info = {}
        if health_row:
            health_info = {
                "state": health_row.state,
                "last_success": str(health_row.last_success),
                "last_failure": str(health_row.last_failure),
                "consecutive_failures": health_row.consecutive_failures or 0,
                "backoff_until": str(health_row.backoff_until)
                if health_row.backoff_until else None,
                "quota_remaining": health_row.quota_remaining,
            }
        out[source] = {
            "qualification": entry.qualification_status,
            "enabled": entry.enabled,
            "priority": entry.priority,
            "health": health_info,
        }
    return out


def _job_summaries(db: Session) -> dict[str, Any]:
    """Per job type: last run, next run, status."""
    out = {}
    for job_type in ALL_JOB_TYPES:
        config = get_job_config(job_type)
        last = db.query(AcquisitionJobRecord).filter(
            AcquisitionJobRecord.job_type == job_type,
            AcquisitionJobRecord.status.in_(["succeeded", "partial", "skipped"])
        ).order_by(AcquisitionJobRecord.completed_at.desc()).first()
        running = db.query(AcquisitionJobRecord).filter(
            AcquisitionJobRecord.job_type == job_type,
            AcquisitionJobRecord.status == "running").count()
        out[job_type] = {
            "enabled": config.get("enabled", True),
            "interval_seconds": config.get("interval_seconds"),
            "priority": config.get("priority", 100),
            "last_run": {
                "job_id": last.job_id if last else None,
                "status": last.status if last else None,
                "completed_at": str(last.completed_at) if last else None,
            } if last else None,
            "running_count": running,
        }
    return out


def _competition_summaries(db: Session) -> dict[str, Any]:
    """Per competition: fixture count, latest observation, freshness."""
    now = _now()
    out = {}
    for league in db.query(League).all():
        fixture_count = db.query(Match).filter(
            Match.league_id == league.id).count()
        future = db.query(Match).filter(
            Match.league_id == league.id,
            Match.kickoff_at > now).count()
        latest_match = db.query(Match).filter(
            Match.league_id == league.id
        ).order_by(Match.kickoff_at.desc()).first()
        out[league.code] = {
            "fixture_count": fixture_count,
            "upcoming": future,
            "latest_observation": str(latest_match.kickoff_at)
            if latest_match else None,
        }
    return out


def _lock_summary(db: Session) -> dict[str, Any]:
    """Active and stale lock counts."""
    now = _now()
    all_locks = db.query(AcquisitionJobLock).all()
    active = 0
    for lock in all_locks:
        expires = lock.expires_at
        if expires and expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires and expires > now:
            active += 1
    return {"total": len(all_locks), "active": active,
            "stale": len(all_locks) - active}


def _recent_runs(db: Session, limit: int = 10) -> list:
    """Most recent job records."""
    records = db.query(AcquisitionJobRecord).order_by(
        AcquisitionJobRecord.id.desc()).limit(limit).all()
    return [{
        "job_id": r.job_id,
        "job_type": r.job_type,
        "competition": r.competition,
        "status": r.status,
        "duration_ms": r.duration_ms,
        "trigger": r.trigger,
        "completed_at": str(r.completed_at),
    } for r in records]
