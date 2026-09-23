"""Phase 28 competition/season breakdown. Read-only, no rankings."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.db.models.evaluation_records import PredictionEvaluationRecord
from app.services.prediction_evaluation.aggregation import (
    MEAN_METRIC_KEYS,
    _mean,
)


def _scope_metrics(rows: list) -> Dict[str, Any]:
    metrics: Dict[str, Any] = {"sample_count": len(rows)}
    for key in MEAN_METRIC_KEYS:
        metrics[key] = _mean([r.metrics.get(key) for r in rows
                              if isinstance(r.metrics, dict)])
    return metrics


def breakdown(
    db: Session,
    *,
    by: str = "competition",
    model_id: Optional[str] = None,
    model_version: Optional[str] = None,
    limit: int = 5000,
) -> Dict[str, Any]:
    """Group evaluation aggregates by competition / season / both."""
    if by not in ("competition", "season", "competition_season"):
        raise ValueError(f"unsupported breakdown: {by!r}")
    query = db.query(PredictionEvaluationRecord)
    if model_id:
        query = query.filter_by(model_id=model_id)
    if model_version:
        query = query.filter_by(model_version=model_version)
    rows = query.order_by(PredictionEvaluationRecord.id.asc()).limit(limit).all()

    def key_of(row) -> str:
        if by == "competition":
            return row.competition or "unknown"
        if by == "season":
            return row.season or "unknown"
        return f"{row.competition or 'unknown'}::{row.season or 'unknown'}"

    groups: Dict[str, List] = {}
    for row in rows:
        groups.setdefault(key_of(row), []).append(row)
    return {
        "by": by,
        "filters": {"model_id": model_id, "model_version": model_version},
        "groups": {name: _scope_metrics(members)
                   for name, members in sorted(groups.items())},
        "note": "measurements with denominators; no competition rankings",
    }
