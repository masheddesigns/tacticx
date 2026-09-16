"""Predictions endpoint (Phase 1: stored predictions only; engine lands in Phase 2)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.db.models.core import Match
from app.db.models.predictions import Prediction
from app.schemas.schemas import PredictionOut

router = APIRouter(tags=["predictions"])


@router.get("/predictions/{match_id}", summary="Stored predictions for a match")
def list_predictions(match_id: int, db: Session = Depends(get_db)):
    if not db.get(Match, match_id):
        raise HTTPException(404, "match not found")
    rows = db.query(Prediction).filter_by(match_id=match_id).order_by(
        Prediction.prediction_timestamp.desc()).all()
    return {"data": [
        PredictionOut(id=r.id, match_id=r.match_id, prediction_timestamp=r.prediction_timestamp,
                      model_version=r.model_version, prediction_type=r.prediction_type,
                      predicted_probability=r.predicted_probability,
                      probabilities=r.probabilities, confidence=r.confidence)
        for r in rows
    ]}
