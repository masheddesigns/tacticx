"""Phase 27 read-only aggregate evaluation services.

Measurements with sample sizes and periods. Never ranks models.
"""
from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.db.models.evaluation_records import PredictionEvaluationRecord

MEAN_METRIC_KEYS = (
    "accuracy_1x2",
    "log_loss_1x2",
    "brier_1x2",
    "goal_mae",
    "total_goal_error",
    "ou_1_5_accuracy",
    "ou_2_5_accuracy",
    "ou_3_5_accuracy",
    "btts_accuracy",
    "exact_score_hit",
)

SE_METRIC_KEYS = (
    "home_goal_se",
    "away_goal_se",
    "total_goal_se",
)


def _mean(values: List[float]) -> Optional[float]:
    vals = [v for v in values if isinstance(v, (int, float))
            and not isinstance(v, bool) and math.isfinite(v)]
    if not vals:
        return None
    return round(sum(vals) / len(vals), 4)


def summarize_evaluations(
    db: Session,
    *,
    model_id: Optional[str] = None,
    model_version: Optional[str] = None,
    competition: Optional[str] = None,
    season: Optional[str] = None,
    prediction_mode: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    limit: int = 5000,
) -> Dict[str, Any]:
    """Aggregate evaluation records. Read-only."""
    query = db.query(PredictionEvaluationRecord)
    if model_id:
        query = query.filter_by(model_id=model_id)
    if model_version:
        query = query.filter_by(model_version=model_version)
    if competition:
        query = query.filter_by(competition=competition)
    if season:
        query = query.filter_by(season=season)
    if prediction_mode:
        query = query.filter_by(prediction_mode=prediction_mode)
    if date_from is not None:
        query = query.filter(PredictionEvaluationRecord.created_at >= date_from)
    if date_to is not None:
        query = query.filter(PredictionEvaluationRecord.created_at <= date_to)
    rows = query.order_by(PredictionEvaluationRecord.id.asc()).limit(limit).all()

    metrics: Dict[str, Any] = {"sample_count": len(rows)}
    for key in MEAN_METRIC_KEYS:
        metrics[key] = _mean([r.metrics.get(key) for r in rows
                              if isinstance(r.metrics, dict)])
    for key in SE_METRIC_KEYS:
        mean_se = _mean([r.metrics.get(key) for r in rows
                         if isinstance(r.metrics, dict)])
        rmse_key = key.replace("_se", "_rmse")
        metrics[rmse_key] = round(math.sqrt(mean_se), 4) \
            if mean_se is not None else None
    home_se = _mean([r.metrics.get("home_goal_se") for r in rows
                     if isinstance(r.metrics, dict)])
    away_se = _mean([r.metrics.get("away_goal_se") for r in rows
                     if isinstance(r.metrics, dict)])
    if home_se is not None and away_se is not None:
        metrics["goal_rmse"] = round(math.sqrt((home_se + away_se) / 2.0), 4)
    else:
        metrics["goal_rmse"] = None

    periods = [r.created_at.isoformat() for r in rows if r.created_at]
    return {
        "filters": {
            "model_id": model_id, "model_version": model_version,
            "competition": competition, "season": season,
            "prediction_mode": prediction_mode,
            "date_from": date_from.isoformat() if date_from else None,
            "date_to": date_to.isoformat() if date_to else None,
        },
        "evaluation_period": {
            "from": min(periods) if periods else None,
            "to": max(periods) if periods else None,
        },
        "metrics": metrics,
    }
