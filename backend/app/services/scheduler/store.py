"""Job store — record persistence, database-backed locking, due calculation.

Locking uses short-lived rows with TTL expiry. Stale locks are recovered
automatically on acquisition. Every operation is deterministic and
idempotent: duplicate runs produce duplicate-count records, not duplicate
canonical data.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.db.models.scheduler import AcquisitionJobLock, AcquisitionJobRecord
from app.services.scheduler.config import (
    ALL_JOB_TYPES,
    DEFAULT_SCHEDULER,
    get_job_config,
    lock_key,
)

# Terminal statuses — jobs in these states are never "running".
TERMINAL = frozenset({"succeeded", "partial", "failed", "skipped",
                       "unavailable", "cancelled", "rate_limited"})


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_record(db: Session, *, job_type: str, source: str = "",
                  competition: str = "", season: str = "",
                  dry_run: bool = False, trigger: str = "scheduler",
                  details: dict | None = None) -> AcquisitionJobRecord:
    """Create an append-only job record (queued status)."""
    job_id = f"{job_type}-{uuid.uuid4().hex[:12]}"
    row = AcquisitionJobRecord(
        job_id=job_id, job_type=job_type, source=source,
        competition=competition, season=season,
        dry_run=1 if dry_run else 0, trigger=trigger,
        details=details, status="queued")
    db.add(row)
    db.commit()
    return row


def mark_running(db: Session, record: AcquisitionJobRecord) -> None:
    record.status = "running"
    record.started_at = _now()
    db.commit()


def mark_terminal(db: Session, record: AcquisitionJobRecord, status: str,
                  **fields) -> None:
    """Mark a record as terminal with optional field updates."""
    if status not in TERMINAL:
        raise ValueError(f"status {status!r} is not terminal")
    record.status = status
    record.completed_at = _now()
    if record.started_at and record.completed_at:
        started = record.started_at.replace(tzinfo=timezone.utc) \
            if record.started_at.tzinfo is None else record.started_at
        completed = record.completed_at.replace(tzinfo=timezone.utc) \
            if record.completed_at.tzinfo is None else record.completed_at
        delta = completed - started
        record.duration_ms = int(delta.total_seconds() * 1000)
    for key, value in fields.items():
        if hasattr(record, key):
            setattr(record, key, value)
    db.commit()


def acquire_lock(db: Session, job_type: str, competition: str = "",
                 ttl_seconds: int | None = None) -> AcquisitionJobLock | None:
    """Try to acquire a database lock. Returns the lock row on success,
    None if another owner holds it. Stale (expired) locks are reclaimed."""
    key = lock_key(job_type, competition)
    config = get_job_config(job_type)
    ttl = ttl_seconds or config.get("lock_ttl_seconds",
                                     DEFAULT_SCHEDULER["lock_ttl_seconds"])
    now = _now()

    # Reclaim expired lock if any.
    existing = db.query(AcquisitionJobLock).filter_by(lock_key=key).first()
    if existing is not None:
        expires = existing.expires_at
        if expires and expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires and expires > now:
            # Lock held by someone else — not expired.
            return None
        # Expired — delete and re-acquire.
        db.delete(existing)
        db.commit()

    owner = f"pid-{uuid.uuid4().hex[:8]}"
    lock = AcquisitionJobLock(
        lock_key=key, owner=owner,
        acquired_at=now, expires_at=now + timedelta(seconds=ttl),
        job_type=job_type, competition=competition)
    db.add(lock)
    db.commit()
    return lock


def release_lock(db: Session, lock: AcquisitionJobLock) -> None:
    """Release a lock safely. Missing lock is not an error."""
    if lock is None:
        return
    existing = db.query(AcquisitionJobLock).filter_by(
        lock_key=lock.lock_key).first()
    if existing is not None and existing.owner == lock.owner:
        db.delete(existing)
        db.commit()


def is_due(db: Session, job_type: str, competition: str = "",
           since: datetime | None = None) -> bool:
    """Check if a job is due: never run or last run > interval ago."""
    config = get_job_config(job_type)
    if not config.get("enabled", True):
        return False
    now = since or _now()
    interval = config.get("interval_seconds", 3600)
    query = db.query(AcquisitionJobRecord).filter(
        AcquisitionJobRecord.job_type == job_type,
        AcquisitionJobRecord.competition == (competition or ""),
        AcquisitionJobRecord.status.in_(["succeeded", "partial", "skipped"]))
    last = query.order_by(AcquisitionJobRecord.completed_at.desc()).first()
    if last is None or last.completed_at is None:
        return True
    completed = last.completed_at.replace(tzinfo=timezone.utc) \
        if last.completed_at.tzinfo is None else last.completed_at
    elapsed = (now - completed).total_seconds()
    return elapsed >= interval


def find_due_jobs(db: Session, since: datetime | None = None) -> list[dict]:
    """Return all due (job_type, competition) pairs sorted by priority."""
    due = []
    for job_type in ALL_JOB_TYPES:
        config = get_job_config(job_type)
        if not config.get("enabled", True):
            continue
        competitions = config.get("competitions", [""])
        for comp in (competitions or [""]):
            if is_due(db, job_type, comp, since=since):
                due.append({
                    "job_type": job_type,
                    "competition": comp,
                    "priority": config.get("priority", 100),
                })
    due.sort(key=lambda d: d["priority"])
    return due


def recent_records(db: Session, *, job_type: str | None = None,
                   source: str | None = None,
                   competition: str | None = None,
                   status: str | None = None,
                   limit: int = 50) -> list[AcquisitionJobRecord]:
    """Query job records with optional filters (most recent first)."""
    query = db.query(AcquisitionJobRecord)
    if job_type:
        query = query.filter(AcquisitionJobRecord.job_type == job_type)
    if source:
        query = query.filter(AcquisitionJobRecord.source == source)
    if competition:
        query = query.filter(AcquisitionJobRecord.competition == competition)
    if status:
        query = query.filter(AcquisitionJobRecord.status == status)
    return query.order_by(AcquisitionJobRecord.id.desc()).limit(limit).all()


def get_record(db: Session, record_id: int) -> AcquisitionJobRecord | None:
    return db.get(AcquisitionJobRecord, record_id)


def cleanup_expired_locks(db: Session) -> int:
    """Delete all expired lock rows. Returns count deleted."""
    now = _now()
    all_locks = db.query(AcquisitionJobLock).all()
    count = 0
    for lock in all_locks:
        expires = lock.expires_at
        if expires and expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires and expires <= now:
            db.delete(lock)
            count += 1
    if count:
        db.commit()
    return count
