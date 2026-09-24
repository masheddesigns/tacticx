"""Phase 30 explicit human approvals (counted, never inferred)."""
from __future__ import annotations

import uuid
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from app.db.models.governance import ModelApprovalRecord

from .artifact import get_artifact
from .contracts import (
    APPROVAL_PENDING,
    APPROVED,
    DECISION_APPROVE,
    DECISION_REJECT,
    PROMOTION_REQUESTED,
    REJECTED,
    REQUIRED_APPROVAL_COUNT,
)
from .lifecycle import log_event, transition
from .promotion import get_request


class ApprovalError(Exception):
    def __init__(self, reason: str, *, code: str = "APPROVAL_ERROR"):
        super().__init__(reason)
        self.reason = reason
        self.code = code


def required_approvals() -> int:
    """Configurable approval count (default 1; no faked identities)."""
    return REQUIRED_APPROVAL_COUNT


def approvals_for_request(db: Session,
                          request_id: str) -> List[ModelApprovalRecord]:
    return (db.query(ModelApprovalRecord)
            .filter_by(request_id=request_id)
            .order_by(ModelApprovalRecord.id.asc()).all())


def decide(
    db: Session,
    request_id: str,
    *,
    decision: str,
    actor: str,
    reason: str = "",
) -> Dict[str, Any]:
    """Record one explicit human decision on a promotion request."""
    if decision not in (DECISION_APPROVE, DECISION_REJECT):
        raise ApprovalError(f"unknown decision: {decision}",
                            code="INVALID_DECISION")
    if not actor:
        raise ApprovalError("actor is required; identities are not invented",
                            code="MISSING_ACTOR")
    request = get_request(db, request_id)
    if request.state not in ("OPEN", "PENDING"):
        raise ApprovalError(
            f"request state {request.state} accepts no more decisions",
            code="REQUEST_CLOSED")
    artifact = get_artifact(db, request.candidate_artifact_id)

    row = ModelApprovalRecord(
        approval_id=f"appr_{uuid.uuid4().hex[:12]}",
        request_id=request_id,
        decision=decision,
        actor=actor,
        reason=reason,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    if decision == DECISION_REJECT:
        request.state = "REJECTED"
        db.commit()
        transition(db, artifact, REJECTED, actor=actor, reason=reason,
                   references={"request_id": request_id,
                               "approval_id": row.approval_id})
    else:
        approvals = approvals_for_request(db, request_id)
        count = sum(1 for a in approvals if a.decision == DECISION_APPROVE)
        if count >= required_approvals():
            request.state = "APPROVED"
            db.commit()
            transition(db, artifact, APPROVED, actor=actor, reason=reason,
                       references={"request_id": request_id,
                                   "approval_id": row.approval_id,
                                   "approval_count": count})
        else:
            request.state = "PENDING"
            db.commit()
            if artifact.lifecycle_state == PROMOTION_REQUESTED:
                transition(db, artifact, APPROVAL_PENDING, actor=actor,
                           reason=reason,
                           references={"request_id": request_id,
                                       "approval_id": row.approval_id})
            else:
                log_event(db, artifact_id=artifact.artifact_id,
                          from_state=artifact.lifecycle_state,
                          to_state=artifact.lifecycle_state,
                          actor=actor, reason=reason,
                          references={"request_id": request_id,
                                      "approval_id": row.approval_id})
    return approval_to_dict(row)


def approval_to_dict(row: ModelApprovalRecord) -> Dict[str, Any]:
    return {
        "approval_id": row.approval_id,
        "request_id": row.request_id,
        "decision": row.decision,
        "actor": row.actor,
        "reason": row.reason,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }
