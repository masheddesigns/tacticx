"""Backtesting service skeleton (Phase 4). Phase 1 scope: immutable prediction
storage + point-in-time input snapshots so 'what did the model know?' is
answerable later. No lookahead: resolution only uses finished-match results."""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.db.models.core import Match
from app.db.models.enums import MatchStatus
from app.db.models.predictions import Prediction, PredictionResult


def record_prediction(db: Session, *, match_id: int, model_version: str, prediction_type: str,
                      predicted_probability: float, probabilities: Optional[dict] = None,
                      confidence: Optional[float] = None, input_snapshot: Optional[dict] = None) -> Prediction:
    row = Prediction(match_id=match_id, model_version=model_version, prediction_type=prediction_type,
                     predicted_probability=predicted_probability, probabilities=probabilities,
                     confidence=confidence, input_snapshot=input_snapshot)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def resolve_predictions(db: Session, match_id: int) -> int:
    """Attach actual results to predictions of a FINISHED match. Never rewrites predictions."""
    match = db.get(Match, match_id)
    if not match or match.status != MatchStatus.FINISHED.value:
        return 0
    if match.home_score is None or match.away_score is None:
        return 0
    if match.home_score > match.away_score:
        actual = "home"
    elif match.home_score < match.away_score:
        actual = "away"
    else:
        actual = "draw"
    n = 0
    for p in db.query(Prediction).filter_by(match_id=match_id).all():
        if db.query(PredictionResult).filter_by(prediction_id=p.id).first():
            continue
        db.add(PredictionResult(prediction_id=p.id, actual_result=actual))
        n += 1
    db.commit()
    return n
