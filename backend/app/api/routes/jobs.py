"""Job scheduler API routes (Phase 20).

GET  /jobs          — list recent job records (filters: job_type, source, competition, status)
GET  /jobs/{job_id} — single job record detail
POST /jobs/{job_type}/run — trigger a job (manual mode, same code path as scheduler)
GET  /jobs/due      — list due jobs without executing
GET  /jobs/alerts   — operational alert conditions
GET  /jobs/anomalies — anomaly detection results
GET  /jobs/dashboard — full operational dashboard
POST /jobs/locks/cleanup — reclaim stale locks
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.config import get_settings
from app.services.scheduler import (
    ALL_JOB_TYPES,
    check_alerts,
    detect_anomalies,
    find_due_jobs,
    run_job_manual,
    scheduler_status,
)
from app.services.scheduler.store import (
    cleanup_expired_locks,
    get_record,
    recent_records,
)

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("")
def list_jobs(
    job_type: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    competition: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    records = recent_records(db, job_type=job_type, source=source,
                             competition=competition, status=status,
                             limit=limit)
    return [{
        "id": r.id, "job_id": r.job_id, "job_type": r.job_type,
        "source": r.source, "competition": r.competition, "season": r.season,
        "requested_at": str(r.requested_at), "started_at": str(r.started_at),
        "completed_at": str(r.completed_at), "status": r.status,
        "request_count": r.request_count, "success_count": r.success_count,
        "failure_count": r.failure_count, "new_observations": r.new_observations,
        "duplicate_observations": r.duplicate_observations,
        "new_matches": r.new_matches, "updated_matches": r.updated_matches,
        "unresolved_identities": r.unresolved_identities,
        "conflicts": r.conflicts, "duration_ms": r.duration_ms,
        "error_code": r.error_code, "dry_run": bool(r.dry_run),
        "trigger": r.trigger,
    } for r in records]


@router.get("/due")
def list_due_jobs(db: Session = Depends(get_db)):
    return find_due_jobs(db)


@router.get("/alerts")
def list_alerts(db: Session = Depends(get_db)):
    return check_alerts(db)


@router.get("/anomalies")
def list_anomalies(db: Session = Depends(get_db)):
    return detect_anomalies(db)


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db)):
    return scheduler_status(db)


@router.post("/locks/cleanup")
def cleanup_locks_endpoint(db: Session = Depends(get_db)):
    if not get_settings().operational_endpoints_enabled:
        raise HTTPException(status_code=403, detail="Operational mutation endpoints are disabled in this environment")
    count = cleanup_expired_locks(db)
    return {"cleaned": count}


@router.get("/{job_id}")
def get_job(job_id: int, db: Session = Depends(get_db)):
    record = get_record(db, job_id)
    if record is None:
        raise HTTPException(status_code=404, detail="job record not found")
    return {
        "id": record.id, "job_id": record.job_id, "job_type": record.job_type,
        "source": record.source, "competition": record.competition,
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


@router.post("/{job_type}/run")
def run_job_endpoint(
    job_type: str,
    competition: str = Query(""),
    season: str = Query(""),
    source: str = Query(""),
    dry_run: bool = Query(False),
    db: Session = Depends(get_db),
):
    if not get_settings().operational_endpoints_enabled:
        raise HTTPException(status_code=403, detail="Operational mutation endpoints are disabled in this environment")
    if job_type not in ALL_JOB_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"unknown job type: {job_type!r}")
    result = run_job_manual(db, job_type, competition=competition,
                            season=season, source=source, dry_run=dry_run)
    return result
