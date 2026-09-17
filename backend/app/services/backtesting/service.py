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
                      confidence: Optional[float] = None, input_snapshot: Optional[dict] = None,
                      model_name: str = "", prediction_cutoff=None,
                      temporal_mode: str = "strict_prematch", status: str = "valid",
                      feature_availability: Optional[dict] = None,
                      model_config: Optional[dict] = None,
                      random_seed: Optional[int] = None) -> Prediction:
    row = Prediction(match_id=match_id, model_version=model_version, prediction_type=prediction_type,
                     predicted_probability=predicted_probability, probabilities=probabilities,
                     confidence=confidence, input_snapshot=input_snapshot,
                     model_name=model_name, prediction_cutoff=prediction_cutoff,
                     temporal_mode=temporal_mode, status=status,
                     feature_availability=feature_availability, model_config=model_config,
                     random_seed=random_seed)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def store_full_prediction(db: Session, match_id: int, prediction,
                            model_config: Optional[dict] = None) -> Prediction:
    """Persist a Phase 2 FullPrediction with its complete audit trail."""
    from datetime import datetime

    cutoff = prediction.prediction_cutoff
    try:
        cutoff_dt = datetime.fromisoformat(cutoff) if cutoff else None
    except (TypeError, ValueError):
        cutoff_dt = None
    probabilities = {
        "home_win": prediction.home_win_probability,
        "draw": prediction.draw_probability,
        "away_win": prediction.away_win_probability,
        "expected_home_goals": prediction.expected_home_goals,
        "expected_away_goals": prediction.expected_away_goals,
        "expected_total_goals": prediction.expected_total_goals,
        "over_1_5": prediction.over_1_5_probability,
        "under_1_5": prediction.under_1_5_probability,
        "over_2_5": prediction.over_2_5_probability,
        "under_2_5": prediction.under_2_5_probability,
        "over_3_5": prediction.over_3_5_probability,
        "under_3_5": prediction.under_3_5_probability,
        "btts_yes": prediction.btts_yes_probability,
        "btts_no": prediction.btts_no_probability,
        "scores": dict(prediction.score_probabilities or {}),
    }
    input_snapshot = {
        "model": prediction.model_name,
        "model_version": prediction.model_version,
        "cutoff": prediction.prediction_cutoff,
        "temporal_mode": prediction.temporal_mode,
        "seed": prediction.random_seed,
        "xg_used": prediction.xg_used,
        "feature_availability": prediction.feature_availability,
        "data_quality": list(prediction.data_quality or []),
        "features": dict(prediction.feature_availability or {}),
    }
    return record_prediction(
        db, match_id=match_id, model_version=prediction.model_version,
        prediction_type="1x2", predicted_probability=prediction.home_win_probability,
        probabilities=probabilities, confidence=prediction.confidence,
        input_snapshot=input_snapshot, model_name=prediction.model_name,
        prediction_cutoff=cutoff_dt, temporal_mode=prediction.temporal_mode,
        status=prediction.status, feature_availability=prediction.feature_availability,
        model_config=model_config, random_seed=prediction.random_seed)


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
