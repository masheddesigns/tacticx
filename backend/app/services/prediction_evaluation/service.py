"""Phase 27 prediction evaluation orchestrator.

Flow: prediction snapshot (read-only) -> verified outcome snapshot ->
metrics -> immutable evaluation record. Evaluation never mutates
prediction snapshots; the prediction hash is re-verified before scoring.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.db.models.core import League, Match
from app.db.models.evaluation_records import PredictionEvaluationRecord
from app.db.models.prediction_snapshots import PreMatchPredictionSnapshot

from .contracts import (
    EVALUATION_CONTRACT_VERSION,
    canonical_hash,
    evaluation_key,
)
from .metrics import score_snapshot
from .outcomes import (
    OutcomeNotReady,
    capture_outcome_snapshot,
    latest_outcome,
    outcome_eligibility,
    outcome_to_dict,
)


class EvaluationBlocked(Exception):
    """Raised when evaluation is refused (no snapshot, no outcome, ...)."""

    def __init__(self, reason: str, *, code: str = "EVALUATION_BLOCKED",
                 details: Optional[Dict[str, Any]] = None):
        super().__init__(reason)
        self.reason = reason
        self.code = code
        self.details = details or {}


def get_snapshot(db: Session, prediction_id: str) -> PreMatchPredictionSnapshot:
    row = (
        db.query(PreMatchPredictionSnapshot)
        .filter_by(prediction_id=prediction_id)
        .first()
    )
    if row is None:
        raise EvaluationBlocked(f"unknown prediction: {prediction_id}",
                                code="UNKNOWN_PREDICTION")
    return row


def find_evaluation(db: Session,
                    evaluation_key_value: str) -> Optional[PredictionEvaluationRecord]:
    return (
        db.query(PredictionEvaluationRecord)
        .filter_by(evaluation_key=evaluation_key_value)
        .order_by(PredictionEvaluationRecord.id.desc())
        .first()
    )


def evaluations_for_prediction(db: Session,
                               prediction_id: str) -> List[PredictionEvaluationRecord]:
    return (
        db.query(PredictionEvaluationRecord)
        .filter_by(prediction_id=prediction_id)
        .order_by(PredictionEvaluationRecord.id.asc())
        .all()
    )


def evaluations_for_match(db: Session, match_id: int) -> List[PredictionEvaluationRecord]:
    from app.services.prediction_execution.store import list_predictions_for_match

    out = []
    for snap in list_predictions_for_match(db, match_id, limit=500):
        out.extend(evaluations_for_prediction(db, snap.prediction_id))
    return out


def evaluate_prediction_snapshot(
    db: Session,
    prediction_id: str,
    *,
    outcome_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Evaluate one immutable prediction snapshot. Idempotent on
    (prediction_id, outcome_hash)."""
    snap = get_snapshot(db, prediction_id)

    # Re-verify prediction integrity before scoring.
    if not snap.prediction_hash or not snap.prediction_payload:
        raise EvaluationBlocked("prediction snapshot is incomplete",
                                code="INCOMPLETE_SNAPSHOT")

    from app.db.models.evaluation_records import MatchOutcomeSnapshot

    if outcome_id is not None:
        outcome = (
            db.query(MatchOutcomeSnapshot)
            .filter_by(outcome_id=outcome_id)
            .first()
        )
        if outcome is None:
            raise EvaluationBlocked(f"unknown outcome: {outcome_id}",
                                    code="UNKNOWN_OUTCOME")
        if outcome.match_id != snap.match_id:
            raise EvaluationBlocked(
                "outcome belongs to a different match",
                code="OUTCOME_MATCH_MISMATCH")
    else:
        try:
            outcome = capture_outcome_snapshot(db, snap.match_id)
        except OutcomeNotReady as exc:
            raise EvaluationBlocked(exc.reason, code=exc.code) from exc

    key = evaluation_key(prediction_id, outcome.outcome_hash)
    existing = find_evaluation(db, key)
    if existing is not None:
        result = evaluation_to_dict(existing)
        result["cache_hit"] = True
        return result

    payload = snap.prediction_payload.get("prediction", {})
    metrics = score_snapshot(payload, outcome.final_home_goals,
                             outcome.final_away_goals)

    match = db.get(Match, snap.match_id)
    league_code, season = None, None
    if match is not None and match.league_id is not None:
        league = db.get(League, match.league_id)
        if league is not None:
            league_code, season = league.code, league.season

    evaluation_payload = {
        "contract": EVALUATION_CONTRACT_VERSION,
        "prediction_id": prediction_id,
        "prediction_hash": snap.prediction_hash,
        "outcome_snapshot_id": outcome.outcome_id,
        "outcome_hash": outcome.outcome_hash,
        "model_id": snap.model_id,
        "model_version": snap.model_version,
        "metrics": metrics,
    }
    evaluation_hash = canonical_hash(evaluation_payload)

    prior = evaluations_for_prediction(db, prediction_id)
    version = len(prior) + 1
    row = PredictionEvaluationRecord(
        evaluation_id=f"eval_{snap.match_id}_{uuid.uuid4().hex[:12]}",
        prediction_id=prediction_id,
        prediction_hash=snap.prediction_hash,
        outcome_snapshot_id=outcome.outcome_id,
        outcome_hash=outcome.outcome_hash,
        model_id=snap.model_id,
        model_version=snap.model_version,
        prediction_mode=snap.prediction_mode,
        competition=league_code,
        season=season,
        prediction_cutoff=snap.cutoff_time,
        kickoff_time=snap.kickoff_time,
        actual_result=metrics["actual_result"],
        actual_home_goals=outcome.final_home_goals,
        actual_away_goals=outcome.final_away_goals,
        metrics=metrics,
        evaluation_version=version,
        evaluation_key=key,
        evaluation_hash=evaluation_hash,
        provenance={
            "contract": EVALUATION_CONTRACT_VERSION,
            "evaluated_at": datetime.now(timezone.utc).replace(
                microsecond=0).isoformat(),
            "outcome": outcome_to_dict(outcome),
            "note": "post-match scoring only; prediction snapshot untouched",
        },
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    result = evaluation_to_dict(row)
    result["cache_hit"] = False
    return result


def evaluation_to_dict(row: PredictionEvaluationRecord) -> Dict[str, Any]:
    return {
        "evaluation_id": row.evaluation_id,
        "prediction_id": row.prediction_id,
        "prediction_hash": row.prediction_hash,
        "outcome_snapshot_id": row.outcome_snapshot_id,
        "outcome_hash": row.outcome_hash,
        "model_id": row.model_id,
        "model_version": row.model_version,
        "prediction_mode": row.prediction_mode,
        "competition": row.competition,
        "season": row.season,
        "prediction_cutoff": row.prediction_cutoff.isoformat()
        if row.prediction_cutoff else None,
        "kickoff_time": row.kickoff_time.isoformat()
        if row.kickoff_time else None,
        "actual_result": row.actual_result,
        "actual_home_goals": row.actual_home_goals,
        "actual_away_goals": row.actual_away_goals,
        "metrics": row.metrics,
        "evaluation_version": row.evaluation_version,
        "evaluation_key": row.evaluation_key,
        "evaluation_hash": row.evaluation_hash,
        "provenance": row.provenance,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def describe_match_evaluation(db: Session, match_id: int) -> Dict[str, Any]:
    """Read-only evaluation status for a match (never creates records)."""
    match = db.get(Match, match_id)
    if match is None:
        raise EvaluationBlocked(f"unknown match: {match_id}",
                                code="UNKNOWN_MATCH")
    from app.services.prediction_execution.store import list_predictions_for_match

    snapshots = list_predictions_for_match(db, match_id, limit=500)
    outcome = latest_outcome(db, match_id)
    eligibility = outcome_eligibility(db, match_id)
    evaluations = evaluations_for_match(db, match_id)
    return {
        "match_id": match_id,
        "match_status": match.status,
        "final_score": {"home": match.home_score, "away": match.away_score},
        "outcome_eligible": eligibility["eligible"],
        "outcome_eligibility_code": eligibility["code"],
        "outcome": outcome_to_dict(outcome) if outcome else None,
        "prediction_count": len(snapshots),
        "evaluation_count": len(evaluations),
        "evaluations": [evaluation_to_dict(e) for e in evaluations],
    }
