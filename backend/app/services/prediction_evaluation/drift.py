"""Phase 27 performance drift monitoring (measure only).

Compares a recent trailing window against a baseline with explicit sample
sizes. Reports measured differences; never labels a model degraded on
intuition, and flags insufficient samples instead of concluding.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.db.models.evaluation_records import PredictionEvaluationRecord

from .aggregation import MEAN_METRIC_KEYS, _mean
from .contracts import MIN_DRIFT_SAMPLE


def _window_rows(db: Session, n: int, **filters) -> list:
    query = db.query(PredictionEvaluationRecord)
    for field in ("model_id", "model_version", "competition", "season",
                  "prediction_mode"):
        value = filters.get(field)
        if value:
            query = query.filter_by(**{field: value})
    return query.order_by(
        PredictionEvaluationRecord.id.desc()).limit(n).all()


def _baseline_rows(db: Session, **filters) -> list:
    query = db.query(PredictionEvaluationRecord)
    for field in ("model_id", "model_version", "competition", "season",
                  "prediction_mode"):
        value = filters.get(field)
        if value:
            query = query.filter_by(**{field: value})
    return query.order_by(
        PredictionEvaluationRecord.id.asc()).limit(5000).all()


def drift_report(
    db: Session,
    *,
    recent_n: int = 50,
    model_id: Optional[str] = None,
    model_version: Optional[str] = None,
    competition: Optional[str] = None,
    season: Optional[str] = None,
    prediction_mode: Optional[str] = None,
) -> Dict[str, Any]:
    """Recent-window vs baseline metric comparison. Read-only."""
    filters = {"model_id": model_id, "model_version": model_version,
               "competition": competition, "season": season,
               "prediction_mode": prediction_mode}
    recent = _window_rows(db, recent_n, **filters)
    baseline = _baseline_rows(db, **filters)

    def means(rows: list) -> Dict[str, Optional[float]]:
        return {k: _mean([r.metrics.get(k) for r in rows
                          if isinstance(r.metrics, dict)])
                for k in MEAN_METRIC_KEYS}

    recent_means, baseline_means = means(recent), means(baseline)
    differences: Dict[str, Optional[float]] = {}
    for key in MEAN_METRIC_KEYS:
        r_val, b_val = recent_means[key], baseline_means[key]
        if r_val is None or b_val is None:
            differences[key] = None
        else:
            differences[key] = round(r_val - b_val, 4)

    recent_period = [r.created_at.isoformat() for r in recent if r.created_at]
    return {
        "recent_n_requested": recent_n,
        "recent_sample": len(recent),
        "baseline_sample": len(baseline),
        "sufficient_sample": len(recent) >= MIN_DRIFT_SAMPLE,
        "min_sample": MIN_DRIFT_SAMPLE,
        "recent_period": {
            "from": min(recent_period) if recent_period else None,
            "to": max(recent_period) if recent_period else None,
        },
        "filters": filters,
        "recent_means": recent_means,
        "baseline_means": baseline_means,
        "differences_recent_minus_baseline": differences,
        "note": "measured differences only; no automatic degradation verdict",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
