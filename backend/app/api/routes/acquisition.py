"""Acquisition operations endpoints (Phase 18, read-only)."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.services.lifecycle.health import get_health

router = APIRouter(prefix="/acquisition", tags=["acquisition"])


@router.get("/status", summary="Acquisition source/competition health")
def acquisition_status(db: Session = Depends(get_db),
                       source: Optional[str] = Query(None)):
    """Source health + latest acquisition runs. No credentials, no payloads."""
    from app.db.models.acquisition import AcquisitionRun

    health = get_health(db, source)
    query = db.query(AcquisitionRun).order_by(AcquisitionRun.id.desc())
    if source:
        query = query.filter(AcquisitionRun.source == source)
    runs = query.limit(20).all()
    return {
        "health": health,
        "recent_runs": [
            {"run_id": r.run_id, "source": r.source, "job": r.job,
             "status": r.status,
             "started_at": str(r.started_at) if r.started_at else None,
             "finished_at": str(r.finished_at) if r.finished_at else None,
             "records_seen": r.records_seen,
             "records_created": r.records_created,
             "records_updated": r.records_updated,
             "records_rejected": r.records_rejected,
             "records_quarantined": r.records_quarantined,
             "errors": r.errors}
            for r in runs
        ],
    }
