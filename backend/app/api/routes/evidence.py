"""Real-world performance evidence API (Phase 33).

Reads are open. Snapshot generation/refresh is append-only evidence
computation guarded by the operational guard. Nothing here mutates
models, authority, predictions, outcomes, or evaluations.
"""
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.config import get_settings
from app.db.models.evidence import EvidenceCohort, EvidenceSnapshot
from app.services.evidence import (
    build_cohort,
    cohort_to_dict,
    compute_evidence,
    generate_snapshot,
    get_cohort,
    get_snapshot,
    snapshot_to_dict,
)
from app.services.evidence.cohort import CohortError
from app.services.evidence.snapshot import EvidenceError

router = APIRouter(prefix="/evidence", tags=["evidence"])


def _guard() -> None:
    if not get_settings().operational_endpoints_enabled:
        raise HTTPException(
            status_code=403,
            detail="Evidence generation endpoints are disabled in this environment")


def _parse_dt(value: Optional[str], name: str) -> Optional[datetime]:
    if value is None:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        raise HTTPException(
            status_code=422, detail=f"{name} must be ISO-8601")


class CohortBody(BaseModel):
    champion_artifact_id: Optional[str] = None
    challenger_artifact_id: Optional[str] = None
    competitions: List[str] = []
    seasons: List[str] = []
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    prediction_mode: str = "PRE_MATCH"


@router.get("/status")
def evidence_status(db: Session = Depends(get_db)):
    from app.db.models.evaluation_records import PredictionEvaluationRecord
    from app.db.models.governance import ShadowEvaluationRecord

    champion_evals = db.query(PredictionEvaluationRecord).count()
    challenger_evals = db.query(ShadowEvaluationRecord).count()
    snapshots = db.query(EvidenceSnapshot).count()
    if champion_evals == 0 and challenger_evals == 0:
        state = "NO_DATA"
    elif challenger_evals == 0:
        state = "INSUFFICIENT_REAL_DATA"
    else:
        state = "AVAILABLE"
    return {
        "state": state,
        "champion_evaluations": champion_evals,
        "challenger_evaluations": challenger_evals,
        "paired_observations": challenger_evals,
        "real_shadow_predictions": challenger_evals,
        "synthetic_observations": 0,
        "evidence_snapshots": snapshots,
    }


@router.get("/cohorts")
def list_cohorts(limit: int = Query(200, ge=1, le=1000),
                 db: Session = Depends(get_db)):
    rows = db.query(EvidenceCohort).order_by(
        EvidenceCohort.id.desc()).limit(limit).all()
    return {"cohorts": [cohort_to_dict(r) for r in rows]}


@router.post("/cohorts", status_code=201)
def create_cohort(body: CohortBody, db: Session = Depends(get_db)):
    _guard()
    try:
        row = build_cohort(
            db, champion_artifact_id=body.champion_artifact_id,
            challenger_artifact_id=body.challenger_artifact_id,
            competitions=body.competitions or None,
            seasons=body.seasons or None,
            date_from=_parse_dt(body.date_from, "date_from"),
            date_to=_parse_dt(body.date_to, "date_to"),
            prediction_mode=body.prediction_mode)
    except CohortError as exc:
        raise HTTPException(status_code=422, detail=exc.reason)
    return cohort_to_dict(row)


@router.get("/cohorts/{cohort_id}")
def cohort_detail(cohort_id: str, db: Session = Depends(get_db)):
    try:
        return cohort_to_dict(get_cohort(db, cohort_id))
    except CohortError as exc:
        raise HTTPException(status_code=404, detail=exc.reason)


@router.get("/snapshots")
def list_snapshots(limit: int = Query(200, ge=1, le=1000),
                   db: Session = Depends(get_db)):
    rows = db.query(EvidenceSnapshot).order_by(
        EvidenceSnapshot.id.desc()).limit(limit).all()
    return {"snapshots": [snapshot_to_dict(r) for r in rows]}


@router.get("/snapshots/{snapshot_id}")
def snapshot_detail(snapshot_id: str, db: Session = Depends(get_db)):
    try:
        return snapshot_to_dict(get_snapshot(db, snapshot_id))
    except EvidenceError as exc:
        raise HTTPException(status_code=404, detail=exc.reason)


@router.get("/compare/{challenger_id}")
def evidence_compare(challenger_id: str, db: Session = Depends(get_db)):
    ephemeral = build_cohort(db, challenger_artifact_id=challenger_id,
                             persist=False)
    return compute_evidence(db, ephemeral)


@router.get("/breakdown/{challenger_id}")
def evidence_breakdown(challenger_id: str,
                       by: str = Query("competition",
                                       pattern="^(competition|season)$"),
                       db: Session = Depends(get_db)):
    from app.services.production_monitoring.breakdown import breakdown

    return breakdown(db, by=by)


@router.get("/uncertainty/{snapshot_id}")
def evidence_uncertainty(snapshot_id: str, db: Session = Depends(get_db)):
    try:
        row = get_snapshot(db, snapshot_id)
    except EvidenceError as exc:
        raise HTTPException(status_code=404, detail=exc.reason)
    return {"snapshot_id": row.snapshot_id,
            "uncertainty": row.uncertainty,
            "paired_count": row.paired_count}


@router.post("/refresh")
def evidence_refresh(
    challenger_artifact_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    _guard()
    row = build_cohort(db, challenger_artifact_id=challenger_artifact_id)
    return generate_snapshot(db, row.cohort_id)
