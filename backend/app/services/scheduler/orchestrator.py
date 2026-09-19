"""Scheduler orchestrator — run_job, run_due, dry-run.

The orchestrator is the single entry point for executing jobs. It handles:
1. Lock acquisition (prevent duplicate concurrent jobs)
2. Job record creation (append-only)
3. Executor dispatch
4. Health/failure recording
5. Lock release (always)

Prediction must never be triggered by the orchestrator.
The orchestrator only maintains data readiness.
"""
from __future__ import annotations

import time
from typing import Any

from sqlalchemy.orm import Session

from app.services.scheduler import store
from app.services.scheduler.config import (
    get_job_config,
)
from app.services.scheduler.executors import get_executor


def run_job(db: Session, job_type: str, *,
            competition: str = "", season: str = "",
            source: str = "", dry_run: bool = False,
            trigger: str = "scheduler",
            force: bool = False) -> dict[str, Any]:
    """Execute one job with locking and append-only recording.

    Returns the job record as a dict. If the lock cannot be acquired
    (concurrent run), returns status="skipped" with the reason.

    force=True skips the due-check and lock (for manual CLI/API runs).
    """
    config = get_job_config(job_type)
    lock = None
    record = None

    try:
        # 1. Lock acquisition (skip if force or dry_run).
        if not force and not dry_run:
            lock = store.acquire_lock(
                db, job_type, competition,
                ttl_seconds=config.get("lock_ttl_seconds", 300))
            if lock is None:
                record = store.create_record(
                    db, job_type=job_type, source=source,
                    competition=competition, season=season,
                    dry_run=dry_run, trigger=trigger,
                    details={"skip_reason": "concurrent job running"})
                store.mark_terminal(db, record, "skipped",
                                    error_code="lock_held")
                return store_to_dict(record)

        # 2. Create job record.
        record = store.create_record(
            db, job_type=job_type, source=source,
            competition=competition, season=season,
            dry_run=dry_run, trigger=trigger)
        store.mark_running(db, record)

        # 3. Execute.
        executor = get_executor(job_type)
        exec_config = dict(config)
        if competition:
            exec_config["competitions"] = [competition]
        if season:
            exec_config["seasons"] = [season]

        start = time.monotonic()
        result = executor(db, exec_config, dry_run=dry_run)
        elapsed_ms = int((time.monotonic() - start) * 1000)

        # 4. Record outcome.
        status = result.get("status", "failed")
        error_code = result.get("error_code", "")
        error_message = result.get("error", "")
        record.duration_ms = elapsed_ms
        record.details = result
        record.request_count = result.get("request_count", 0)
        record.success_count = result.get("success_count", 0)
        record.failure_count = result.get("failures", 0)
        record.new_observations = result.get("new_observations", 0)
        record.duplicate_observations = result.get("duplicate_observations", 0)
        record.new_matches = result.get("new_matches", 0)
        record.updated_matches = result.get("updated_matches", 0)
        record.unresolved_identities = result.get("unresolved_identities", 0)
        record.conflicts = result.get("conflicts", 0)
        record.error_code = error_code
        record.error_message = str(error_message)[:500]

        # Map executor statuses to terminal statuses.
        terminal = {
            "succeeded": "succeeded",
            "partial": "partial",
            "failed": "failed",
            "dry_run": "succeeded",
            "skipped": "skipped",
            "unavailable": "unavailable",
            "rate_limited": "rate_limited",
            "empty": "succeeded",
        }
        store.mark_terminal(db, record, terminal.get(status, "failed"))
        return store_to_dict(record)

    except Exception as exc:
        # 5. Exception → record failure, release lock, re-raise.
        if record is not None:
            try:
                record.error_code = type(exc).__name__
                record.error_message = str(exc)[:500]
                store.mark_terminal(db, record, "failed")
            except Exception:  # noqa: BLE001,S110 — defensive error recording
                pass
        raise

    finally:
        # 6. Always release lock.
        store.release_lock(db, lock)


def run_due(db: Session, *, dry_run: bool = False,
            trigger: str = "scheduler") -> list[dict[str, Any]]:
    """Find and execute all due jobs in priority order. Returns list of
    job record dicts."""
    due_jobs = store.find_due_jobs(db)
    results = []
    for entry in due_jobs:
        result = run_job(
            db, entry["job_type"],
            competition=entry.get("competition", ""),
            dry_run=dry_run, trigger=trigger)
        results.append(result)
    return results


def run_job_manual(db: Session, job_type: str, *,
                   competition: str = "", season: str = "",
                   source: str = "", dry_run: bool = False) -> dict[str, Any]:
    """Manual execution via CLI/API. Skips due-check, uses force mode."""
    return run_job(db, job_type, competition=competition, season=season,
                   source=source, dry_run=dry_run,
                   trigger="manual", force=True)


def store_to_dict(record) -> dict[str, Any]:
    """Convert a job record to a response-safe dict."""
    return {
        "id": record.id,
        "job_id": record.job_id,
        "job_type": record.job_type,
        "source": record.source,
        "competition": record.competition,
        "season": record.season,
        "requested_at": str(record.requested_at),
        "started_at": str(record.started_at),
        "completed_at": str(record.completed_at),
        "status": record.status,
        "plan_hash": record.plan_hash,
        "qualification_hash": record.qualification_hash,
        "request_count": record.request_count,
        "success_count": record.success_count,
        "failure_count": record.failure_count,
        "new_observations": record.new_observations,
        "duplicate_observations": record.duplicate_observations,
        "new_matches": record.new_matches,
        "updated_matches": record.updated_matches,
        "unresolved_identities": record.unresolved_identities,
        "conflicts": record.conflicts,
        "duration_ms": record.duration_ms,
        "error_code": record.error_code,
        "error_message": record.error_message,
        "dry_run": bool(record.dry_run),
        "trigger": record.trigger,
        "details": record.details,
    }
