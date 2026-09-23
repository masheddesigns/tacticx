"""Phase 27 production calibration analysis (measure only).

Deterministic equal-width reliability bins per 1X2 outcome, reusing the
Phase 2 reliability definitions. Never recalibrates the production model.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.db.models.evaluation_records import PredictionEvaluationRecord
from app.services.backtesting import metrics as met

OUTCOMES = ("home", "draw", "away")


def calibration_report(
    db: Session,
    *,
    model_id: Optional[str] = None,
    model_version: Optional[str] = None,
    competition: Optional[str] = None,
    season: Optional[str] = None,
    n_bins: int = 10,
    limit: int = 5000,
) -> Dict[str, Any]:
    """Per-outcome reliability curves + ECE. Read-only, deterministic."""
    query = db.query(PredictionEvaluationRecord)
    if model_id:
        query = query.filter_by(model_id=model_id)
    if model_version:
        query = query.filter_by(model_version=model_version)
    if competition:
        query = query.filter_by(competition=competition)
    if season:
        query = query.filter_by(season=season)
    rows = query.order_by(PredictionEvaluationRecord.id.asc()).limit(limit).all()

    per_outcome: Dict[str, Any] = {}
    for outcome in OUTCOMES:
        probs: List[float] = []
        labels: List[int] = []
        for row in rows:
            m = row.metrics if isinstance(row.metrics, dict) else {}
            p = m.get(f"p_{outcome}")
            if not isinstance(p, (int, float)) or isinstance(p, bool):
                continue
            probs.append(float(p))
            labels.append(1 if m.get("actual_result") == outcome else 0)
        per_outcome[outcome] = {
            "sample_count": len(probs),
            "reliability": met.reliability_curve(probs, labels, n_bins=n_bins),
            "ece": met.expected_calibration_error(probs, labels, n_bins=n_bins),
        }
    return {
        "n_bins": n_bins,
        "sample_count": len(rows),
        "filters": {"model_id": model_id, "model_version": model_version,
                    "competition": competition, "season": season},
        "per_outcome": per_outcome,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
