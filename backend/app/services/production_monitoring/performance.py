"""Phase 28 production performance overview + temporal windows.

Read-only aggregations over immutable evaluation records. Every metric
carries its sample size; empty scopes return explicit empty states.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.db.models.evaluation_records import PredictionEvaluationRecord
from app.services.prediction_evaluation.aggregation import summarize_evaluations

from .contracts import (
    METRIC_DEFINITION_VERSION,
    MONITORING_CONTRACT_VERSION,
    bootstrap_mean_ci,
    wilson_interval,
)

WINDOW_PRESETS = (20, 50, 100)


def _window_rows(db: Session, n: int, **filters) -> list:
    query = db.query(PredictionEvaluationRecord)
    for field in ("model_id", "model_version", "competition", "season",
                  "prediction_mode"):
        value = filters.get(field)
        if value:
            query = query.filter_by(**{field: value})
    return query.order_by(
        PredictionEvaluationRecord.id.desc()).limit(n).all()


def _window_summary(rows: list) -> Dict[str, Any]:
    from app.services.prediction_evaluation.aggregation import (
        MEAN_METRIC_KEYS,
        _mean,
    )

    metrics: Dict[str, Any] = {"sample_count": len(rows)}
    for key in MEAN_METRIC_KEYS:
        metrics[key] = _mean([r.metrics.get(key) for r in rows
                              if isinstance(r.metrics, dict)])
    # Wilson interval for hit-rate accuracy (proportion with trials).
    acc_vals = [r.metrics.get("accuracy_1x2") for r in rows
                if isinstance(r.metrics, dict)
                and r.metrics.get("accuracy_1x2") in (0, 1)]
    metrics["accuracy_1x2_ci"] = wilson_interval(sum(acc_vals), len(acc_vals))
    # Seeded bootstrap CI for Brier mean (scalar, practical).
    brier_vals = [r.metrics.get("brier_1x2") for r in rows
                  if isinstance(r.metrics, dict)
                  and isinstance(r.metrics.get("brier_1x2"), (int, float))]
    metrics["brier_1x2_ci"] = bootstrap_mean_ci(brier_vals)
    periods = [r.created_at.isoformat() for r in rows if r.created_at]
    return {
        "metrics": metrics,
        "period": {"from": min(periods) if periods else None,
                   "to": max(periods) if periods else None},
    }


def performance_overview(
    db: Session,
    *,
    model_id: Optional[str] = None,
    model_version: Optional[str] = None,
    competition: Optional[str] = None,
    season: Optional[str] = None,
    prediction_mode: Optional[str] = None,
) -> Dict[str, Any]:
    """Full-scope aggregate (delegates metric math to Phase 27 summary)."""
    summary = summarize_evaluations(
        db, model_id=model_id, model_version=model_version,
        competition=competition, season=season,
        prediction_mode=prediction_mode)
    summary["contract"] = MONITORING_CONTRACT_VERSION
    summary["metric_definition_version"] = METRIC_DEFINITION_VERSION
    return summary


def temporal_windows(
    db: Session,
    *,
    windows: Optional[List[int]] = None,
    model_id: Optional[str] = None,
    model_version: Optional[str] = None,
    competition: Optional[str] = None,
    season: Optional[str] = None,
    prediction_mode: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Trailing-N windows + optional custom date range. Read-only."""
    filters = {"model_id": model_id, "model_version": model_version,
               "competition": competition, "season": season,
               "prediction_mode": prediction_mode}
    windows = list(windows) if windows else list(WINDOW_PRESETS)
    out: Dict[str, Any] = {"windows": {}, "filters": filters}
    for n in windows:
        rows = _window_rows(db, n, **filters)
        if date_from is not None or date_to is not None:
            from app.services.features.temporal import as_naive_utc

            naive_from = as_naive_utc(date_from)
            naive_to = as_naive_utc(date_to)
            rows = [r for r in rows
                    if (naive_from is None
                        or (as_naive_utc(r.created_at) is not None
                            and as_naive_utc(r.created_at) >= naive_from))
                    and (naive_to is None
                         or (as_naive_utc(r.created_at) is not None
                             and as_naive_utc(r.created_at) <= naive_to))]
        window = _window_summary(rows)
        window["window_n"] = n
        window["sufficient_sample"] = len(rows) >= 20
        out["windows"][str(n)] = window
    if date_from is not None or date_to is not None:
        custom = summarize_evaluations(
            db, model_id=model_id, model_version=model_version,
            competition=competition, season=season,
            prediction_mode=prediction_mode,
            date_from=date_from, date_to=date_to)
        out["custom_range"] = custom
    out["contract"] = MONITORING_CONTRACT_VERSION
    out["metric_definition_version"] = METRIC_DEFINITION_VERSION
    return out
