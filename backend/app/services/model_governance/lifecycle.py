"""Phase 30 lifecycle transitions + append-only event log."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.db.models.governance import ModelArtifact, ModelGovernanceEvent

from .contracts import ALLOWED_TRANSITIONS


class GovernanceError(Exception):
    def __init__(self, reason: str, *, code: str = "GOVERNANCE_ERROR"):
        super().__init__(reason)
        self.reason = reason
        self.code = code


def allowed_transitions(state: str) -> tuple:
    return ALLOWED_TRANSITIONS.get(state, ())


def log_event(
    db: Session,
    *,
    artifact_id: Optional[str],
    from_state: str,
    to_state: str,
    actor: str,
    reason: str = "",
    references: Optional[Dict[str, Any]] = None,
) -> ModelGovernanceEvent:
    row = ModelGovernanceEvent(
        event_id=f"gov_{uuid.uuid4().hex[:12]}",
        artifact_id=artifact_id,
        from_state=from_state,
        to_state=to_state,
        actor=actor,
        reason=reason,
        references=references or {},
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def transition(
    db: Session,
    artifact: ModelArtifact,
    to_state: str,
    *,
    actor: str,
    reason: str = "",
    references: Optional[Dict[str, Any]] = None,
) -> ModelArtifact:
    """Validate and apply a lifecycle transition (append-only event)."""
    from_state = artifact.lifecycle_state
    if to_state not in allowed_transitions(from_state):
        raise GovernanceError(
            f"transition {from_state} -> {to_state} is not allowed",
            code="INVALID_TRANSITION")
    artifact.lifecycle_state = to_state
    db.commit()
    db.refresh(artifact)
    log_event(db, artifact_id=artifact.artifact_id,
              from_state=from_state, to_state=to_state,
              actor=actor, reason=reason, references=references)
    return artifact


def events_for_artifact(db: Session,
                        artifact_id: str) -> List[ModelGovernanceEvent]:
    return (db.query(ModelGovernanceEvent)
            .filter_by(artifact_id=artifact_id)
            .order_by(ModelGovernanceEvent.id.asc()).all())


def event_to_dict(row: ModelGovernanceEvent) -> Dict[str, Any]:
    return {
        "event_id": row.event_id,
        "artifact_id": row.artifact_id,
        "from_state": row.from_state,
        "to_state": row.to_state,
        "actor": row.actor,
        "reason": row.reason,
        "references": row.references,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def audit_trail(db: Session, artifact_id: Optional[str] = None,
                limit: int = 500) -> List[Dict[str, Any]]:
    query = db.query(ModelGovernanceEvent)
    if artifact_id:
        query = query.filter_by(artifact_id=artifact_id)
    rows = query.order_by(ModelGovernanceEvent.id.desc()).limit(limit).all()
    return [event_to_dict(r) for r in rows]


def recorded_at() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
