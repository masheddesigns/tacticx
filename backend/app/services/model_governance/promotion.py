"""Phase 30 explicit promotion requests (never self-activating)."""
from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.db.models.governance import ModelPromotionRequest, ModelValidationReport

from .artifact import get_artifact
from .contracts import (
    CHALLENGER,
    DEPLOYMENT_CANARY,
    DEPLOYMENT_PRODUCTION,
    DEPLOYMENT_SHADOW,
    PROMOTION_REQUESTED,
    VALIDATED,
    VALIDATION_VALIDATED,
)
from .lifecycle import transition


class PromotionError(Exception):
    def __init__(self, reason: str, *, code: str = "PROMOTION_ERROR"):
        super().__init__(reason)
        self.reason = reason
        self.code = code


ALLOWED_DEPLOYMENT_MODES = (DEPLOYMENT_SHADOW, DEPLOYMENT_CANARY,
                            DEPLOYMENT_PRODUCTION)


def request_promotion(
    db: Session,
    artifact_id: str,
    *,
    validation_id: str,
    competition: Optional[str] = None,
    season: Optional[str] = None,
    prediction_mode: str = "PRE_MATCH",
    deployment_mode: str = DEPLOYMENT_SHADOW,
    requester: str = "",
    reason: str = "",
) -> Dict[str, Any]:
    """Request promotion. Moves VALIDATED/CHALLENGER artifact to
    PROMOTION_REQUESTED. Never activates production."""
    artifact = get_artifact(db, artifact_id)
    if artifact.lifecycle_state not in (VALIDATED, CHALLENGER):
        raise PromotionError(
            f"artifact state {artifact.lifecycle_state} cannot be promoted; "
            "validate first", code="INVALID_ARTIFACT_STATE")
    if artifact.lifecycle_state == VALIDATED:
        # Register the challenger role first (strict machine order:
        # VALIDATED -> CHALLENGER -> PROMOTION_REQUESTED).
        from .registry import bind_challenger

        transition(db, artifact, CHALLENGER,
                   actor=requester or "system",
                   reason="challenger registered on promotion request")
        bind_challenger(db, artifact_id, competition=competition,
                        season=season, prediction_mode=prediction_mode)
    if deployment_mode not in ALLOWED_DEPLOYMENT_MODES:
        raise PromotionError(f"unknown deployment mode: {deployment_mode}",
                             code="INVALID_DEPLOYMENT_MODE")
    report = db.query(ModelValidationReport).filter_by(
        validation_id=validation_id).first()
    if report is None:
        raise PromotionError(f"unknown validation: {validation_id}",
                             code="UNKNOWN_VALIDATION")
    if report.candidate_artifact_id != artifact_id:
        raise PromotionError("validation belongs to a different artifact",
                             code="VALIDATION_MISMATCH")
    if report.validation_result != VALIDATION_VALIDATED:
        raise PromotionError(
            f"validation result {report.validation_result} does not permit "
            "promotion", code="VALIDATION_NOT_PASSED")

    from .registry import current_champion

    champion = current_champion(db, competition=competition, season=season,
                                prediction_mode=prediction_mode)
    row = ModelPromotionRequest(
        request_id=f"promo_{uuid.uuid4().hex[:12]}",
        candidate_artifact_id=artifact_id,
        validation_id=validation_id,
        champion_artifact_id=champion.artifact_id,
        competition=competition,
        season=season,
        prediction_mode=prediction_mode,
        deployment_mode=deployment_mode,
        requester=requester,
        reason=reason,
        state="OPEN",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    transition(db, artifact, PROMOTION_REQUESTED,
               actor=requester or "system", reason=reason,
               references={"request_id": row.request_id,
                           "expected_champion_artifact_id": champion.artifact_id})
    return promotion_to_dict(row)


def get_request(db: Session, request_id: str) -> ModelPromotionRequest:
    row = db.query(ModelPromotionRequest).filter_by(
        request_id=request_id).first()
    if row is None:
        raise PromotionError(f"unknown promotion request: {request_id}",
                             code="UNKNOWN_REQUEST")
    return row


def promotion_to_dict(row: ModelPromotionRequest) -> Dict[str, Any]:
    return {
        "request_id": row.request_id,
        "candidate_artifact_id": row.candidate_artifact_id,
        "validation_id": row.validation_id,
        "champion_artifact_id": row.champion_artifact_id,
        "competition": row.competition,
        "season": row.season,
        "prediction_mode": row.prediction_mode,
        "deployment_mode": row.deployment_mode,
        "requester": row.requester,
        "reason": row.reason,
        "state": row.state,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def list_requests(db: Session, state: Optional[str] = None,
                  limit: int = 200) -> List[Dict[str, Any]]:
    query = db.query(ModelPromotionRequest)
    if state:
        query = query.filter_by(state=state)
    rows = query.order_by(ModelPromotionRequest.id.desc()).limit(limit).all()
    return [promotion_to_dict(r) for r in rows]
