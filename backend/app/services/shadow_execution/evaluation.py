"""Phase 32 shadow evaluation: shared-outcome scoring for both arms.

Champion metrics mirror the linked Phase 27 evaluation record;
challenger metrics use the same score_snapshot implementation against
the SAME outcome snapshot. Differences are factual only.
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.db.models.core import Match
from app.db.models.governance import ShadowEvaluationRecord, ShadowPredictionSnapshot
from app.services.prediction_evaluation.metrics import score_snapshot

from .contracts import canonical_hash


class ShadowEvaluationError(Exception):
    def __init__(self, reason: str, *, code: str = "SHADOW_EVALUATION_ERROR"):
        super().__init__(reason)
        self.reason = reason
        self.code = code


def evaluate_shadow_pair(
    db: Session,
    shadow_id: str,
    *,
    outcome_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Score one shadow pair against the shared verified outcome."""
    from app.db.models.evaluation_records import MatchOutcomeSnapshot
    from app.services.prediction_evaluation.outcomes import (
        OutcomeNotReady,
        capture_outcome_snapshot,
    )

    row = db.query(ShadowPredictionSnapshot).filter_by(
        shadow_id=shadow_id).first()
    if row is None:
        raise ShadowEvaluationError(f"unknown shadow: {shadow_id}",
                                    code="UNKNOWN_SHADOW")
    match = db.get(Match, row.match_id)
    if match is None:
        raise ShadowEvaluationError("match missing", code="UNKNOWN_MATCH")

    if outcome_id is not None:
        outcome = db.query(MatchOutcomeSnapshot).filter_by(
            outcome_id=outcome_id).first()
        if outcome is None:
            raise ShadowEvaluationError(f"unknown outcome: {outcome_id}",
                                        code="UNKNOWN_OUTCOME")
        if outcome.match_id != row.match_id:
            raise ShadowEvaluationError("outcome belongs to a different match",
                                        code="OUTCOME_MATCH_MISMATCH")
    else:
        try:
            outcome = capture_outcome_snapshot(db, row.match_id)
        except OutcomeNotReady as exc:
            raise ShadowEvaluationError(exc.reason,
                                        code=exc.code) from exc

    existing = db.query(ShadowEvaluationRecord).filter_by(
        shadow_id=shadow_id, outcome_hash=outcome.outcome_hash).first()
    if existing is not None:
        result = shadow_evaluation_to_dict(existing)
        result["cache_hit"] = True
        return result

    champion_metrics = score_snapshot(
        row.champion_output or {}, outcome.final_home_goals,
        outcome.final_away_goals)
    challenger_metrics = score_snapshot(
        row.challenger_output or {}, outcome.final_home_goals,
        outcome.final_away_goals)
    differences = _differences(champion_metrics, challenger_metrics)
    evaluation_hash = canonical_hash({
        "contract": "SHADOW_EVALUATION_V1",
        "shadow_id": shadow_id,
        "outcome_hash": outcome.outcome_hash,
        "champion_metrics": champion_metrics,
        "challenger_metrics": challenger_metrics,
    })
    record = ShadowEvaluationRecord(
        evaluation_id=f"sheval_{uuid.uuid4().hex[:12]}",
        shadow_id=shadow_id,
        match_id=row.match_id,
        challenger_artifact_id=row.challenger_artifact_id,
        champion_artifact_id=row.champion_artifact_id,
        outcome_snapshot_id=outcome.outcome_id,
        outcome_hash=outcome.outcome_hash,
        champion_metrics=champion_metrics,
        challenger_metrics=challenger_metrics,
        differences=differences,
        sample_note="single-pair scoring; aggregate before concluding",
        evaluation_hash=evaluation_hash,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    _mark_evaluated(db, row)
    result = shadow_evaluation_to_dict(record)
    result["cache_hit"] = False
    return result


def _differences(champion: Dict[str, Any],
                 challenger: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for key in ("accuracy_1x2", "log_loss_1x2", "brier_1x2", "goal_mae",
                "total_goal_error", "ou_1_5_accuracy", "ou_2_5_accuracy",
                "ou_3_5_accuracy", "btts_accuracy", "exact_score_hit"):
        champ_v, chal_v = champion.get(key), challenger.get(key)
        if isinstance(champ_v, (int, float)) and not isinstance(champ_v, bool) \
                and isinstance(chal_v, (int, float)) \
                and not isinstance(chal_v, bool):
            out[f"delta_{key}"] = round(chal_v - champ_v, 6)
        else:
            out[f"delta_{key}"] = None
    out["note"] = "challenger minus champion; factual differences only"
    return out


def _mark_evaluated(db: Session, row: ShadowPredictionSnapshot) -> None:
    row.evaluation_state = "EVALUATED"
    db.commit()


def evaluations_for_challenger(
    db: Session,
    challenger_artifact_id: str,
    limit: int = 500,
) -> List[ShadowEvaluationRecord]:
    return (db.query(ShadowEvaluationRecord)
            .filter_by(challenger_artifact_id=challenger_artifact_id)
            .order_by(ShadowEvaluationRecord.id.asc())
            .limit(limit).all())


def shadow_evaluation_to_dict(row: ShadowEvaluationRecord) -> Dict[str, Any]:
    return {
        "evaluation_id": row.evaluation_id,
        "shadow_id": row.shadow_id,
        "match_id": row.match_id,
        "challenger_artifact_id": row.challenger_artifact_id,
        "champion_artifact_id": row.champion_artifact_id,
        "outcome_snapshot_id": row.outcome_snapshot_id,
        "outcome_hash": row.outcome_hash,
        "champion_metrics": row.champion_metrics,
        "challenger_metrics": row.challenger_metrics,
        "differences": row.differences,
        "sample_note": row.sample_note,
        "evaluation_hash": row.evaluation_hash,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }
