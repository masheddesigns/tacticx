"""Phase 32 shadow monitoring (read-only; never triggers governance).

Surfaces shadow coverage, execution/evaluation completeness, and
aggregate champion-vs-challenger differences with sample sizes.
Factual differences only — no winner declaration.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.db.models.governance import (
    ShadowEvaluationRecord,
    ShadowPredictionSnapshot,
)

from .contracts import SHADOW_CONTRACT_VERSION


def _mean(values: List[Any]) -> Optional[float]:
    vals = [v for v in values if isinstance(v, (int, float))
            and not isinstance(v, bool) and math.isfinite(v)]
    if not vals:
        return None
    return round(sum(vals) / len(vals), 4)


def shadow_summary(
    db: Session,
    *,
    challenger_artifact_id: Optional[str] = None,
    limit: int = 5000,
) -> Dict[str, Any]:
    """Coverage + completeness for shadow execution (read-only)."""
    query = db.query(ShadowPredictionSnapshot)
    if challenger_artifact_id:
        query = query.filter_by(challenger_artifact_id=challenger_artifact_id)
    shadows = query.order_by(ShadowPredictionSnapshot.id.asc()).limit(limit).all()

    eval_query = db.query(ShadowEvaluationRecord)
    if challenger_artifact_id:
        eval_query = eval_query.filter_by(
            challenger_artifact_id=challenger_artifact_id)
    evals = eval_query.order_by(ShadowEvaluationRecord.id.asc()).limit(limit).all()
    evaluated_shadow_ids = {e.shadow_id for e in evals}

    by_challenger: Dict[str, Dict[str, int]] = {}
    for row in shadows:
        entry = by_challenger.setdefault(
            row.challenger_artifact_id, {"executed": 0, "evaluated": 0})
        entry["executed"] += 1
        if row.shadow_id in evaluated_shadow_ids:
            entry["evaluated"] += 1

    return {
        "contract": SHADOW_CONTRACT_VERSION,
        "shadow_executions": len(shadows),
        "shadow_evaluations": len(evals),
        "evaluation_coverage_rate": (
            round(len(evals) / len(shadows), 4) if shadows else None),
        "by_challenger": by_challenger,
        "note": "read-only; monitoring never promotes, demotes, or rolls back",
    }


def shadow_comparison(
    db: Session,
    challenger_artifact_id: str,
    limit: int = 5000,
) -> Dict[str, Any]:
    """Aggregate champion-vs-challenger differences (read-only)."""
    evals = (db.query(ShadowEvaluationRecord)
             .filter_by(challenger_artifact_id=challenger_artifact_id)
             .order_by(ShadowEvaluationRecord.id.asc())
             .limit(limit).all())
    n = len(evals)
    agg: Dict[str, Any] = {"sample_count": n}
    keys = ("accuracy_1x2", "log_loss_1x2", "brier_1x2", "goal_mae",
            "total_goal_error", "ou_2_5_accuracy", "btts_accuracy",
            "exact_score_hit")
    for key in keys:
        champ_vals = [(e.champion_metrics or {}).get(key) for e in evals]
        chal_vals = [(e.challenger_metrics or {}).get(key) for e in evals]
        agg[f"champion_{key}"] = _mean(champ_vals)
        agg[f"challenger_{key}"] = _mean(chal_vals)
        diffs = [(e.differences or {}).get(f"delta_{key}") for e in evals]
        agg[f"delta_{key}"] = _mean(diffs)
    agg["evidence"] = "INSUFFICIENT_DATA" if n < 20 else "MEASURED"
    agg["note"] = ("factual differences with denominators; "
                   "no winner declaration")
    matches = sorted({e.match_id for e in evals})
    return {
        "contract": SHADOW_CONTRACT_VERSION,
        "challenger_artifact_id": challenger_artifact_id,
        "evaluated_pairs": n,
        "matches": matches[:500],
        "aggregate": agg,
    }
