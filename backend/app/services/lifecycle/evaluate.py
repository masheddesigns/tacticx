"""Post-match evaluation (Phase 7).

Finished match + locked prediction -> evaluation record. Evaluation never
mutates the prediction. Only FINISHED matches with recorded scores are
eligible; postponed/cancelled matches are never evaluated as outcomes.
Idempotent: an existing PredictionEvaluation row is returned, never duplicated.
"""
from __future__ import annotations

import math
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.db.models.core import Match
from app.db.models.enums import MatchStatus
from app.db.models.lifecycle import PredictionEvaluation
from app.db.models.predictions import Prediction
from app.services.backtesting.service import resolve_predictions
from app.services.ingestion import SyncStats


def _result(home: int, away: int) -> str:
    if home > away:
        return "home"
    if home < away:
        return "away"
    return "draw"


def evaluate_prediction(db: Session, prediction_id: int) -> Optional[Dict]:
    """Evaluate one stored prediction against its finished match."""
    pred = db.get(Prediction, prediction_id)
    if pred is None:
        return None
    existing = db.query(PredictionEvaluation).filter_by(
        prediction_id=prediction_id).first()
    if existing is not None:
        return _evaluation_out(existing)
    match = db.get(Match, pred.match_id)
    if match is None or match.status != MatchStatus.FINISHED.value:
        return None
    if match.home_score is None or match.away_score is None:
        return None
    probs = pred.probabilities or {}
    home = probs.get("home_win", pred.predicted_probability)
    draw = probs.get("draw")
    away = probs.get("away_win")
    metrics: Dict = {}
    actual = _result(match.home_score, match.away_score)
    if home is not None and draw is not None and away is not None:
        total = home + draw + away
        if total > 0:
            home, draw, away = home / total, draw / total, away / total
            index = {"home": 0, "draw": 1, "away": 2}[actual]
            picked = [home, draw, away][index]
            metrics["accuracy"] = 1 if index == max(range(3),
                                                    key=lambda i: [home, draw, away][i]) else 0
            metrics["log_loss"] = round(-math.log(max(picked, 1e-12)), 6)
            metrics["brier"] = round(sum((p - (1 if i == index else 0)) ** 2
                                         for i, p in enumerate([home, draw, away])), 6)
    exp_home = probs.get("expected_home_goals")
    exp_away = probs.get("expected_away_goals")
    if exp_home is not None and exp_away is not None:
        metrics["goal_mae"] = round((abs(exp_home - match.home_score)
                                     + abs(exp_away - match.away_score)) / 2.0, 4)
        metrics["goal_rmse"] = round(math.sqrt(
            ((exp_home - match.home_score) ** 2
             + (exp_away - match.away_score) ** 2) / 2.0), 4)
    row = PredictionEvaluation(
        prediction_id=prediction_id, match_id=match.id,
        actual_home_goals=match.home_score, actual_away_goals=match.away_score,
        actual_result=actual, metrics=metrics)
    db.add(row)
    db.commit()
    resolve_predictions(db, match.id)
    return _evaluation_out(row)


def evaluate_completed_predictions(db: Session, match_ids: Optional[List[int]] = None,
                                   limit: int = 500) -> SyncStats:
    """Evaluate all unevaluated predictions of finished matches. Idempotent."""
    from app.services.ingestion import _log_sync

    stats, start = SyncStats(), time.monotonic()
    query = db.query(Prediction)
    if match_ids is not None:
        query = query.filter(Prediction.match_id.in_(match_ids))
    for pred in query.order_by(Prediction.id.asc()).limit(limit).all():
        stats.received += 1
        try:
            if db.query(PredictionEvaluation).filter_by(prediction_id=pred.id).first():
                stats.skipped += 1
                continue
            match = db.get(Match, pred.match_id)
            if match is None or match.status != MatchStatus.FINISHED.value:
                stats.skipped += 1
                continue
            if match.home_score is None or match.away_score is None:
                stats.skipped += 1
                continue
            evaluate_prediction(db, pred.id)
            stats.inserted += 1
        except Exception as exc:
            db.rollback()
            stats.errors.append(str(exc)[:300])
    _log_sync(db, "evaluator", "evaluate_completed", stats,
              duration=time.monotonic() - start)
    return stats


def _evaluation_out(row: PredictionEvaluation) -> Dict:
    return {"id": row.id, "prediction_id": row.prediction_id,
            "match_id": row.match_id, "actual_home_goals": row.actual_home_goals,
            "actual_away_goals": row.actual_away_goals,
            "actual_result": row.actual_result, "metrics": row.metrics,
            "evaluated_at": str(row.evaluated_at)}
