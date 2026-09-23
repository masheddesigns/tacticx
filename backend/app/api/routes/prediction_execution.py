"""Pre-match prediction execution API routes (Phase 26).

POST /matches/{match_id}/predictions — execute (or replay) a cutoff-safe
    pre-match prediction bound to the latest Phase 25.1 readiness certificate.
GET  /matches/{match_id}/prediction-snapshots — execution status + history.
GET  /prediction-snapshots/{prediction_id} — single immutable snapshot.
    (Distinct paths: GET /matches/{match_id}/predictions is owned by the
    lifecycle router; GET /predictions/{match_id} by the legacy predictions
    router.)
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.services.acquisition.readiness_gate import DEFAULT_MODEL_ID
from app.services.prediction_execution import (
    PredictionBlocked,
    describe_match_predictions,
    execute_pre_match_prediction,
    get_prediction,
)
from app.services.prediction_execution.store import list_predictions_for_match

router = APIRouter(tags=["prediction-execution"])


class ExecutePredictionRequest(BaseModel):
    cutoff: Optional[str] = None
    model_id: str = DEFAULT_MODEL_ID
    certificate_id: Optional[str] = None
    with_intelligence: bool = False


def _blocked_response(exc: PredictionBlocked) -> dict:
    return {
        "executed": False,
        "blocked": True,
        "code": exc.code,
        "reason": exc.reason,
        "details": exc.details,
    }


@router.post("/matches/{match_id}/predictions")
def execute_prediction(match_id: int, body: ExecutePredictionRequest,
                       db: Session = Depends(get_db)):
    try:
        cutoff = datetime.fromisoformat(body.cutoff) if body.cutoff else None
    except ValueError:
        raise HTTPException(status_code=422, detail="cutoff must be ISO-8601")
    if cutoff is None:
        raise HTTPException(
            status_code=422, detail="cutoff is required (ISO-8601)")
    try:
        result = execute_pre_match_prediction(
            db, match_id, cutoff, model_id=body.model_id,
            certificate_id=body.certificate_id,
            with_intelligence=body.with_intelligence)
    except PredictionBlocked as exc:
        return _blocked_response(exc)
    result["executed"] = True
    result["blocked"] = False
    return result


@router.get("/matches/{match_id}/prediction-snapshots")
def match_predictions(match_id: int, limit: int = Query(50, ge=1, le=200),
                      db: Session = Depends(get_db)):
    try:
        status = describe_match_predictions(db, match_id)
    except PredictionBlocked as exc:
        raise HTTPException(status_code=404, detail=exc.reason)
    rows = list_predictions_for_match(db, match_id, limit=limit)
    status["snapshots"] = [{
        "prediction_id": r.prediction_id,
        "prediction_version": r.prediction_version,
        "model_id": r.model_id,
        "model_version": r.model_version,
        "cutoff_time": r.cutoff_time.isoformat() if r.cutoff_time else None,
        "readiness_state": r.readiness_state,
        "prediction_hash": r.prediction_hash,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    } for r in rows]
    return status


@router.get("/prediction-snapshots/{prediction_id}")
def prediction_detail(prediction_id: str, db: Session = Depends(get_db)):
    try:
        return get_prediction(db, prediction_id)
    except PredictionBlocked as exc:
        raise HTTPException(status_code=404, detail=exc.reason)
