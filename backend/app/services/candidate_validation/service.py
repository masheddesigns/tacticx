"""Phase 34 validation runs: rule evaluation, reports, staleness.

Writes candidate_validation_reports only. Never creates promotion
requests, approvals, activations, rollbacks, or governance transitions.
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from app.db.models.evidence import EvidenceSnapshot
from app.db.models.candidate_validation import CandidateValidationReport
from app.services.evidence import get_snapshot

from .contracts import (
    DEFAULT_CONFIG_ID,
    RULE_BLOCKED,
    RULE_INCONCLUSIVE,
    RULE_INSUFFICIENT,
    RULE_WARNING,
    STATE_BLOCKED,
    STATE_INCONCLUSIVE,
    STATE_INSUFFICIENT,
    STATE_VALIDATED,
    canonical_hash,
    get_config,
)
from .rules import evaluate_rules


class ValidationRunError(Exception):
    def __init__(self, reason: str, *, code: str = "VALIDATION_RUN_ERROR"):
        super().__init__(reason)
        self.reason = reason
        self.code = code


def _summarize(rules: List[Dict[str, Any]], snapshot: EvidenceSnapshot,
               config: Dict[str, Any]) -> Dict[str, Any]:
    by_state: Dict[str, int] = {}
    for rule in rules:
        by_state[rule["state"]] = by_state.get(rule["state"], 0) + 1
    blocked = [r["rule_id"] for r in rules if r["state"] == RULE_BLOCKED]
    warnings = {r["rule_id"]: r["explanation"] for r in rules
                if r["state"] == RULE_WARNING}
    if blocked:
        state = STATE_BLOCKED
    elif by_state.get(RULE_INSUFFICIENT, 0):
        state = STATE_INSUFFICIENT
    elif snapshot.evidence_state in ("SUPPORTED_DIFFERENCE", "INCONCLUSIVE"):
        inconclusive_rules = by_state.get(RULE_INCONCLUSIVE, 0)
        state = STATE_VALIDATED if not inconclusive_rules else STATE_INCONCLUSIVE
    else:
        state = STATE_INCONCLUSIVE
    return {"state": state, "by_state": by_state, "blocked": blocked,
            "warnings": warnings}


def run_validation(
    db: Session,
    candidate_artifact_id: str,
    evidence_snapshot_id: str,
    *,
    config_id: str = DEFAULT_CONFIG_ID,
) -> Dict[str, Any]:
    """Evaluate all gates and persist an immutable validation report."""
    from app.services.model_governance.artifact import get_artifact
    from app.services.model_governance.lifecycle import GovernanceError
    from app.services.model_governance.registry import current_champion

    config = get_config(config_id)
    try:
        get_artifact(db, candidate_artifact_id)
    except GovernanceError as exc:
        raise ValidationRunError(exc.reason, code="UNKNOWN_CANDIDATE") from exc
    try:
        snapshot = get_snapshot(db, evidence_snapshot_id)
    except Exception as exc:
        raise ValidationRunError(str(exc),
                                 code="UNKNOWN_EVIDENCE_SNAPSHOT") from exc
    try:
        champion = current_champion(db)
    except GovernanceError as exc:
        raise ValidationRunError(exc.reason, code="NO_CHAMPION") from exc

    rules = evaluate_rules(
        db, snapshot=snapshot,
        candidate_artifact_id=candidate_artifact_id,
        champion_artifact_id=champion.artifact_id,
        config=config)
    summary = _summarize(rules, snapshot, config)

    semantic = {
        "contract": "CANDIDATE_VALIDATION_V1",
        "candidate_artifact_id": candidate_artifact_id,
        "champion_artifact_id": champion.artifact_id,
        "evidence_snapshot_id": snapshot.snapshot_id,
        "evidence_snapshot_hash": snapshot.snapshot_hash,
        "config_id": config["config_id"],
        "config_version": config["config_version"],
        "rule_results": rules,
        "validation_state": summary["state"],
        "calculation_version": "validation_calc_v1",
    }
    validation_hash = canonical_hash(semantic)
    existing = db.query(CandidateValidationReport).filter_by(
        validation_hash=validation_hash).first()
    if existing is not None:
        result = validation_to_dict(existing)
        result["rerun"] = True
        return result

    row = CandidateValidationReport(
        validation_id=f"val_{uuid.uuid4().hex[:12]}",
        candidate_artifact_id=candidate_artifact_id,
        champion_artifact_id=champion.artifact_id,
        evidence_snapshot_id=snapshot.snapshot_id,
        evidence_snapshot_hash=snapshot.snapshot_hash,
        validation_config_id=config["config_id"],
        validation_config_version=config["config_version"],
        validation_state=summary["state"],
        evidence_state=snapshot.evidence_state,
        rule_results={"rules": rules, "by_state": summary["by_state"]},
        performance_summary={
            "champion": snapshot.champion_metrics,
            "challenger": snapshot.challenger_metrics,
            "differences": snapshot.differences},
        uncertainty_summary=snapshot.uncertainty,
        data_quality_summary=snapshot.data_quality,
        temporal_summary=snapshot.temporal_audit,
        compatibility_summary=_compat_summary(rules),
        operational_summary=_operational_summary(rules),
        blocking_reasons={"rules": summary["blocked"]},
        warnings=summary["warnings"],
        validation_hash=validation_hash,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    result = validation_to_dict(row)
    result["rerun"] = False
    return result


def _compat_summary(rules: List[Dict[str, Any]]) -> Dict[str, Any]:
    for rule in rules:
        if rule["rule_id"] == "PREDICTION_SCHEMA_COMPATIBILITY":
            return {"state": rule["state"],
                    "explanation": rule["explanation"]}
    return {}


def _operational_summary(rules: List[Dict[str, Any]]) -> Dict[str, Any]:
    for rule in rules:
        if rule["rule_id"] == "OPERATIONAL_HEALTH":
            return {"state": rule["state"],
                    "explanation": rule["explanation"],
                    "measured": rule["measured_value"]}
    return {}


def check_staleness(db: Session, validation_id: str) -> Dict[str, Any]:
    """VALID / STALE / SUPERSEDED for a stored validation report."""
    from app.services.model_governance.registry import current_champion

    row = db.query(CandidateValidationReport).filter_by(
        validation_id=validation_id).first()
    if row is None:
        raise ValidationRunError(f"unknown validation: {validation_id}",
                                 code="UNKNOWN_VALIDATION")
    try:
        champion = current_champion(db)
        champion_now = champion.artifact_id
    except Exception:
        champion_now = None
    newer = db.query(CandidateValidationReport).filter(
        CandidateValidationReport.candidate_artifact_id == row.candidate_artifact_id,
        CandidateValidationReport.id > row.id).count()
    if newer:
        state = "SUPERSEDED"
        reason = "a newer validation exists for this candidate"
    elif champion_now != row.champion_artifact_id:
        state = "STALE"
        reason = "champion changed since validation"
    else:
        state = "VALID"
        reason = "champion and evidence binding unchanged"
    return {"validation_id": validation_id, "staleness": state,
            "reason": reason,
            "champion_then": row.champion_artifact_id,
            "champion_now": champion_now}


def validation_to_dict(row: CandidateValidationReport) -> Dict[str, Any]:
    return {
        "validation_id": row.validation_id,
        "candidate_artifact_id": row.candidate_artifact_id,
        "champion_artifact_id": row.champion_artifact_id,
        "evidence_snapshot_id": row.evidence_snapshot_id,
        "evidence_snapshot_hash": row.evidence_snapshot_hash,
        "validation_config_id": row.validation_config_id,
        "validation_config_version": row.validation_config_version,
        "validation_state": row.validation_state,
        "evidence_state": row.evidence_state,
        "rule_results": row.rule_results,
        "performance_summary": row.performance_summary,
        "uncertainty_summary": row.uncertainty_summary,
        "data_quality_summary": row.data_quality_summary,
        "temporal_summary": row.temporal_summary,
        "compatibility_summary": row.compatibility_summary,
        "operational_summary": row.operational_summary,
        "blocking_reasons": row.blocking_reasons,
        "warnings": row.warnings,
        "validation_hash": row.validation_hash,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def get_validation(db: Session, validation_id: str) -> CandidateValidationReport:
    row = db.query(CandidateValidationReport).filter_by(
        validation_id=validation_id).first()
    if row is None:
        raise ValidationRunError(f"unknown validation: {validation_id}",
                                 code="UNKNOWN_VALIDATION")
    return row
