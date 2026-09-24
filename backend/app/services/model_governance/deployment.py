"""Phase 30 canary eligibility, production activation, and rollback.

Activation changes the governance authority binding only; it never edits
prediction code, historical snapshots, or default execution paths (those
stay pinned — see docs/PHASE30_DESIGN_AUDIT.md). Optimistic concurrency
via expected champion match; stale champions fail safely.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.db.models.governance import ModelApprovalRecord

from .artifact import get_artifact
from .contracts import (
    APPROVED,
    CANARY_ELIGIBLE,
    MIN_SHADOW_PAIRS,
    PRODUCTION_ACTIVE,
    REQUIRED_APPROVAL_COUNT,
    ROLE_CHAMPION,
    ROLLED_BACK,
    SHADOW,
    SUPERSEDED,
)
from .lifecycle import GovernanceError, log_event, transition
from .registry import (
    current_champion,
    supersede_binding,
)
from .shadow import shadow_pairs


class DeploymentError(Exception):
    def __init__(self, reason: str, *, code: str = "DEPLOYMENT_ERROR"):
        super().__init__(reason)
        self.reason = reason
        self.code = code


def check_canary_eligibility(
    db: Session,
    artifact_id: str,
    *,
    min_shadow_pairs: int = MIN_SHADOW_PAIRS,
) -> Dict[str, Any]:
    """Explicit canary checklist (no automatic activation)."""
    from app.db.models.governance import ModelPromotionRequest

    artifact = get_artifact(db, artifact_id)
    checks: Dict[str, Any] = {}
    checks["artifact_exists"] = True
    checks["state_shadow_or_approved"] = artifact.lifecycle_state in (
        SHADOW, APPROVED, CANARY_ELIGIBLE)
    requests = db.query(ModelPromotionRequest).filter_by(
        candidate_artifact_id=artifact_id).all()
    approved_request = next(
        (r for r in requests if r.state == "APPROVED"), None)
    checks["approval_exists"] = approved_request is not None
    approvals = 0
    if approved_request is not None:
        approvals = db.query(ModelApprovalRecord).filter_by(
            request_id=approved_request.request_id,
            decision="APPROVE").count()
    checks["approval_count"] = approvals
    checks["approvals_sufficient"] = approvals >= REQUIRED_APPROVAL_COUNT
    pairs = shadow_pairs(db, artifact_id, limit=10000)
    checks["shadow_pairs"] = len(pairs)
    checks["shadow_evidence_sufficient"] = len(pairs) >= min_shadow_pairs
    try:
        from app.services.production_monitoring import detect_anomalies

        anomalies = detect_anomalies(db)
        critical = [a for a in anomalies.get("anomalies", [])
                    if a.get("severity") == "CRITICAL"]
    except Exception:
        critical = []
    checks["critical_anomalies"] = len(critical)
    checks["no_blocking_anomaly"] = len(critical) == 0
    try:
        current_champion(db)
        checks["champion_known"] = True
    except GovernanceError:
        checks["champion_known"] = False
    checks["rollback_target_exists"] = checks["champion_known"]
    eligible = all([
        checks["state_shadow_or_approved"],
        checks["approval_exists"],
        checks["approvals_sufficient"],
        checks["shadow_evidence_sufficient"],
        checks["no_blocking_anomaly"],
        checks["champion_known"],
        checks["rollback_target_exists"],
    ])
    return {"artifact_id": artifact_id, "eligible": eligible,
            "checks": checks,
            "note": "eligibility only; activation remains an explicit operation"}


def mark_canary_eligible(
    db: Session,
    artifact_id: str,
    *,
    actor: str = "",
    min_shadow_pairs: int = MIN_SHADOW_PAIRS,
) -> Dict[str, Any]:
    """Record CANARY_ELIGIBLE after an explicit eligibility check."""
    report = check_canary_eligibility(
        db, artifact_id, min_shadow_pairs=min_shadow_pairs)
    if not report["eligible"]:
        raise DeploymentError(
            "canary eligibility checklist failed",
            code="CANARY_NOT_ELIGIBLE")
    artifact = get_artifact(db, artifact_id)
    if artifact.lifecycle_state == SHADOW:
        transition(db, artifact, CANARY_ELIGIBLE, actor=actor or "system",
                   reason="canary eligibility confirmed",
                   references={"checks": report["checks"]})
    report["state"] = artifact.lifecycle_state
    return report


def activate_production(
    db: Session,
    artifact_id: str,
    *,
    actor: str,
    expected_champion_artifact_id: str,
    reason: str = "",
    competition: Optional[str] = None,
    season: Optional[str] = None,
    prediction_mode: str = "PRE_MATCH",
) -> Dict[str, Any]:
    """Explicit production activation with optimistic concurrency.

    Fails safely when the champion changed since the promotion request.
    Changes the registry binding + lifecycle states only.
    """
    from app.db.models.governance import ModelRegistry

    if not actor:
        raise DeploymentError("actor is required", code="MISSING_ACTOR")
    artifact = get_artifact(db, artifact_id)
    if artifact.lifecycle_state != CANARY_ELIGIBLE:
        raise DeploymentError(
            f"artifact state {artifact.lifecycle_state} cannot activate "
            "production; complete canary eligibility first",
            code="INVALID_ARTIFACT_STATE")
    current = current_champion(db, competition=competition, season=season,
                               prediction_mode=prediction_mode)
    if current.artifact_id != expected_champion_artifact_id:
        raise DeploymentError(
            "champion changed since promotion request; refusing to "
            "overwrite the newer champion",
            code="STALE_CHAMPION")
    if current.artifact_id == artifact_id:
        raise DeploymentError("artifact is already the active champion",
                              code="ALREADY_ACTIVE")

    old_artifact = get_artifact(db, current.artifact_id)
    new_binding = ModelRegistry(
        role=ROLE_CHAMPION, competition=competition, season=season,
        prediction_mode=prediction_mode, artifact_id=artifact_id,
        state="ACTIVE")
    db.add(new_binding)
    db.commit()
    db.refresh(new_binding)
    supersede_binding(db, current, new_id=new_binding.id)

    if old_artifact.lifecycle_state == PRODUCTION_ACTIVE:
        transition(db, old_artifact, SUPERSEDED, actor=actor,
                   reason=f"superseded by {artifact_id}",
                   references={"new_champion_artifact_id": artifact_id})
    transition(db, artifact, PRODUCTION_ACTIVE, actor=actor, reason=reason,
               references={"registry_id": new_binding.id,
                           "previous_champion_artifact_id": current.artifact_id})
    return {
        "artifact_id": artifact_id,
        "registry_id": new_binding.id,
        "previous_champion_artifact_id": current.artifact_id,
        "state": PRODUCTION_ACTIVE,
    }


def rollback(
    db: Session,
    *,
    actor: str,
    target_artifact_id: str,
    reason: str = "",
    competition: Optional[str] = None,
    season: Optional[str] = None,
    prediction_mode: str = "PRE_MATCH",
) -> Dict[str, Any]:
    """Explicit rollback to a prior champion (new event, no rewrites)."""
    from app.db.models.governance import ModelRegistry

    if not actor:
        raise DeploymentError("actor is required", code="MISSING_ACTOR")
    target = get_artifact(db, target_artifact_id)
    current = current_champion(db, competition=competition, season=season,
                               prediction_mode=prediction_mode)
    if current.artifact_id == target_artifact_id:
        raise DeploymentError("target is already the active champion",
                              code="ALREADY_ACTIVE")
    current_artifact = get_artifact(db, current.artifact_id)
    new_binding = ModelRegistry(
        role=ROLE_CHAMPION, competition=competition, season=season,
        prediction_mode=prediction_mode, artifact_id=target_artifact_id,
        state="ACTIVE")
    db.add(new_binding)
    db.commit()
    db.refresh(new_binding)
    supersede_binding(db, current, new_id=new_binding.id)

    if current_artifact.lifecycle_state == PRODUCTION_ACTIVE:
        transition(db, current_artifact, ROLLED_BACK, actor=actor,
                   reason=reason,
                   references={"rollback_target": target_artifact_id})
    else:
        log_event(db, artifact_id=current_artifact.artifact_id,
                  from_state=current_artifact.lifecycle_state,
                  to_state=current_artifact.lifecycle_state,
                  actor=actor, reason=f"rollback superseded: {reason}",
                  references={"rollback_target": target_artifact_id})
    if target.lifecycle_state == SUPERSEDED:
        transition(db, target, PRODUCTION_ACTIVE, actor=actor,
                   reason=f"restored as champion: {reason}",
                   references={"registry_id": new_binding.id})
    else:
        log_event(db, artifact_id=target_artifact_id,
                  from_state=target.lifecycle_state,
                  to_state=target.lifecycle_state, actor=actor,
                  reason=f"restored as champion: {reason}",
                  references={"registry_id": new_binding.id})
    return {
        "artifact_id": target_artifact_id,
        "registry_id": new_binding.id,
        "previous_champion_artifact_id": current.artifact_id,
        "state": target.lifecycle_state,
    }


def activation_history(db: Session, limit: int = 200) -> List[Dict[str, Any]]:
    from .lifecycle import audit_trail

    return audit_trail(db, limit=limit)
