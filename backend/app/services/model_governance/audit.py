"""Phase 30 governance reconstruction: answer every audit question."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.db.models.governance import (
    ModelApprovalRecord,
    ModelPromotionRequest,
    ModelValidationReport,
)

from .artifact import artifact_to_dict, get_artifact
from .lifecycle import audit_trail
from .registry import current_champion


def reconstruct(db: Session, artifact_id: str) -> Dict[str, Any]:
    """Reconstruct the full governance story of one artifact."""
    artifact = get_artifact(db, artifact_id)
    validations = (db.query(ModelValidationReport)
                   .filter_by(candidate_artifact_id=artifact_id)
                   .order_by(ModelValidationReport.id.asc()).all())
    requests = (db.query(ModelPromotionRequest)
                .filter_by(candidate_artifact_id=artifact_id)
                .order_by(ModelPromotionRequest.id.asc()).all())
    approvals: List[Dict[str, Any]] = []
    for req in requests:
        for appr in (db.query(ModelApprovalRecord)
                     .filter_by(request_id=req.request_id)
                     .order_by(ModelApprovalRecord.id.asc()).all()):
            approvals.append({
                "approval_id": appr.approval_id,
                "request_id": appr.request_id,
                "decision": appr.decision,
                "actor": appr.actor,
                "reason": appr.reason,
                "created_at": appr.created_at.isoformat()
                if appr.created_at else None,
            })
    return {
        "artifact": artifact_to_dict(artifact),
        "validations": [{
            "validation_id": v.validation_id,
            "validation_result": v.validation_result,
            "experiment_id": v.experiment_id,
            "dataset_hash": v.dataset_hash,
            "evidence_state": v.evidence_state,
            "leakage_status": v.leakage_status,
            "report_hash": v.report_hash,
            "created_at": v.created_at.isoformat() if v.created_at else None,
        } for v in validations],
        "promotion_requests": [{
            "request_id": r.request_id,
            "validation_id": r.validation_id,
            "champion_artifact_id": r.champion_artifact_id,
            "deployment_mode": r.deployment_mode,
            "requester": r.requester,
            "reason": r.reason,
            "state": r.state,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        } for r in requests],
        "approvals": approvals,
        "events": audit_trail(db, artifact_id=artifact_id),
    }


def champion_lineage(db: Session, limit: int = 200) -> List[Dict[str, Any]]:
    """Activation history with previous-champion linkage."""
    from .deployment import activation_history

    return activation_history(db, limit=limit)


def active_champion_view(
    db: Session,
    *,
    competition: Optional[str] = None,
    season: Optional[str] = None,
    prediction_mode: str = "PRE_MATCH",
) -> Dict[str, Any]:
    """Current production authority answer for a scope."""
    binding = current_champion(db, competition=competition, season=season,
                               prediction_mode=prediction_mode)
    artifact = get_artifact(db, binding.artifact_id)
    return {
        "role": binding.role,
        "competition": binding.competition,
        "season": binding.season,
        "prediction_mode": binding.prediction_mode,
        "artifact": artifact_to_dict(artifact),
        "registry_id": binding.id,
        "bound_at": binding.created_at.isoformat()
        if binding.created_at else None,
    }
