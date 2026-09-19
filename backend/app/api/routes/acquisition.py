"""Acquisition operations endpoints (Phase 18, extended Phase 19)."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.db.models.qualification import SourceQualification
from app.services.provider_qualification import health_ext

router = APIRouter(prefix="/acquisition", tags=["acquisition"])


@router.get("/status", summary="Acquisition source/competition health")
def acquisition_status(db: Session = Depends(get_db),
                       source: Optional[str] = Query(None)):
    """Source health + latest acquisition runs + qualification + freshness
    + coverage. No credentials, no payloads."""
    from app.db.models.acquisition import AcquisitionRun
    from app.services.freshness import audit as audit_svc

    health = health_ext.describe(db, source)
    query = db.query(AcquisitionRun).order_by(AcquisitionRun.id.desc())
    if source:
        query = query.filter(AcquisitionRun.source == source)
    runs = query.limit(20).all()
    qualifications = {}
    for qual in db.query(SourceQualification).order_by(
            SourceQualification.id.desc()).limit(20).all():
        if source and qual.source != source:
            continue
        qualifications.setdefault(qual.source, []).append(
            {"status": qual.status, "competition": qual.competition,
             "season": qual.season, "fixture_count": qual.fixture_count,
             "retrieved_at": str(qual.retrieved_at)})
    try:
        coverage = audit_svc.current_season_audit(db)
    except Exception:
        coverage = {"status": "unavailable"}
    return {
        "health": health,
        "qualifications": qualifications,
        "freshness": {name: (entry.get("last_observed_fixture")
                             if isinstance(entry, dict) else None)
                      for name, entry in health.items()},
        "coverage": coverage,
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
