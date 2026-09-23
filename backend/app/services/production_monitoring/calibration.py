"""Phase 28 calibration monitoring: buckets + ECE + MCE.

Bucket methodology (reliability_buckets_v1): deterministic equal-width
bins over [0,1] (n_bins=10 default), last bin closed on both ends.
Per 1X2 outcome: mean predicted vs empirical frequency per bin, ECE =
count-weighted mean error, MCE = maximum bin error. Measure only.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.db.models.evaluation_records import PredictionEvaluationRecord
from app.services.backtesting import metrics as met

from .contracts import (
    BUCKET_DEFINITION_VERSION,
    CALIBRATION_BINS,
    METRIC_DEFINITION_VERSION,
    MONITORING_CONTRACT_VERSION,
    max_calibration_error,
    wilson_interval,
)

OUTCOMES = ("home", "draw", "away")


def calibration_detail(
    db: Session,
    *,
    model_id: Optional[str] = None,
    model_version: Optional[str] = None,
    competition: Optional[str] = None,
    season: Optional[str] = None,
    n_bins: int = CALIBRATION_BINS,
    limit: int = 5000,
) -> Dict[str, Any]:
    """Per-outcome reliability with ECE, MCE, and per-bin Wilson CIs."""
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
        curve = met.reliability_curve(probs, labels, n_bins=n_bins)
        for b in curve["bins"]:
            b["frequency_ci"] = wilson_interval(
                round(b["empirical_rate"] * b["count"])
                if b["empirical_rate"] is not None else 0, b["count"]) \
                if b["count"] else None
        per_outcome[outcome] = {
            "sample_count": len(probs),
            "buckets": curve["bins"],
            "ece": met.expected_calibration_error(probs, labels, n_bins=n_bins),
            "mce": max_calibration_error(curve),
        }
    return {
        "contract": MONITORING_CONTRACT_VERSION,
        "metric_definition_version": METRIC_DEFINITION_VERSION,
        "bucket_definition_version": BUCKET_DEFINITION_VERSION,
        "bucket_methodology": "deterministic equal-width bins over [0,1]; "
                              "last bin closed on both ends",
        "n_bins": n_bins,
        "sample_count": len(rows),
        "filters": {"model_id": model_id, "model_version": model_version,
                    "competition": competition, "season": season},
        "per_outcome": per_outcome,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
