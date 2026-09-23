"""Prediction evaluation API routes (Phase 27, read-only).

GET  /matches/{match_id}/evaluation — outcome + evaluations for a match.
GET  /prediction-snapshots/{prediction_id}/evaluation — evaluations for one
     snapshot (does not create records; scheduler/service creates them).
GET  /evaluations/summary — aggregate metrics with filters.
GET  /evaluations/calibration — per-outcome reliability + ECE.
GET  /evaluations/drift — recent-window vs baseline comparison.

No endpoint here modifies historical predictions.
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.services.prediction_evaluation import (
    EvaluationBlocked,
    calibration_report,
    describe_match_evaluation,
    drift_report,
    evaluations_for_prediction,
    evaluation_to_dict,
    summarize_evaluations,
)

router = APIRouter(tags=["prediction-evaluation"])


@router.get("/matches/{match_id}/evaluation")
def match_evaluation(match_id: int, db: Session = Depends(get_db)):
    try:
        return describe_match_evaluation(db, match_id)
    except EvaluationBlocked as exc:
        raise HTTPException(status_code=404, detail=exc.reason)


@router.get("/prediction-snapshots/{prediction_id}/evaluation")
def prediction_evaluation(prediction_id: str, db: Session = Depends(get_db)):
    rows = evaluations_for_prediction(db, prediction_id)
    if not rows:
        return {"prediction_id": prediction_id, "evaluation_count": 0,
                "evaluations": []}
    return {"prediction_id": prediction_id, "evaluation_count": len(rows),
            "evaluations": [evaluation_to_dict(r) for r in rows]}


def _parse_dt(value: Optional[str], name: str) -> Optional[datetime]:
    if value is None:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        raise HTTPException(
            status_code=422, detail=f"{name} must be ISO-8601")


@router.get("/evaluations/summary")
def evaluations_summary(
    model_id: Optional[str] = Query(None),
    model_version: Optional[str] = Query(None),
    competition: Optional[str] = Query(None),
    season: Optional[str] = Query(None),
    prediction_mode: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    return summarize_evaluations(
        db, model_id=model_id, model_version=model_version,
        competition=competition, season=season,
        prediction_mode=prediction_mode,
        date_from=_parse_dt(date_from, "date_from"),
        date_to=_parse_dt(date_to, "date_to"))


@router.get("/evaluations/calibration")
def evaluations_calibration(
    model_id: Optional[str] = Query(None),
    model_version: Optional[str] = Query(None),
    competition: Optional[str] = Query(None),
    season: Optional[str] = Query(None),
    n_bins: int = Query(10, ge=2, le=50),
    db: Session = Depends(get_db),
):
    return calibration_report(
        db, model_id=model_id, model_version=model_version,
        competition=competition, season=season, n_bins=n_bins)


@router.get("/evaluations/drift")
def evaluations_drift(
    recent_n: int = Query(50, ge=1, le=1000),
    model_id: Optional[str] = Query(None),
    model_version: Optional[str] = Query(None),
    competition: Optional[str] = Query(None),
    season: Optional[str] = Query(None),
    prediction_mode: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    return drift_report(
        db, recent_n=recent_n, model_id=model_id,
        model_version=model_version, competition=competition,
        season=season, prediction_mode=prediction_mode)
