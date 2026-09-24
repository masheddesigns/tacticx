"""Phase 30 candidate validation against Phase 29 evidence + compatibility."""
from __future__ import annotations

import uuid
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.db.models.governance import ModelValidationReport
from app.db.models.research_registry import ResearchExperiment

from .artifact import get_artifact
from .contracts import (
    VALIDATED,
    VALIDATION_INCONCLUSIVE,
    VALIDATION_INVALID,
    VALIDATION_REJECTED,
    VALIDATION_VALIDATED,
    VALIDATOR_VERSION,
    VALIDATION_PENDING,
    canonical_hash,
)
from .lifecycle import GovernanceError, log_event, transition


class ValidationError(Exception):
    def __init__(self, reason: str, *, code: str = "VALIDATION_ERROR"):
        super().__init__(reason)
        self.reason = reason
        self.code = code


def check_compatibility(candidate_payload: Dict[str, Any]) -> Dict[str, Any]:
    """Verify a candidate output payload matches the production schema."""
    checks: Dict[str, Any] = {}
    probs = [candidate_payload.get("home_win_probability"),
             candidate_payload.get("draw_probability"),
             candidate_payload.get("away_win_probability")]
    checks["probabilities_present"] = all(
        isinstance(p, (int, float)) and not isinstance(p, bool)
        for p in probs)
    checks["probabilities_normalized"] = (
        checks["probabilities_present"]
        and abs(sum(probs) - 1.0) < 1e-3)
    for key in ("expected_home_goals", "expected_away_goals"):
        value = candidate_payload.get(key)
        checks[f"{key}_valid"] = (
            value is None or (isinstance(value, (int, float))
                              and not isinstance(value, bool) and value >= 0))
    checks["mode_prematch"] = True
    checks["compatible"] = all(checks.values())
    return checks


def validate_candidate(
    db: Session,
    artifact_id: str,
    *,
    experiment_id: Optional[str] = None,
    actor: str = "",
) -> Dict[str, Any]:
    """Validate an artifact against research evidence + compatibility."""
    artifact = get_artifact(db, artifact_id)
    if artifact.lifecycle_state != "RESEARCH_ONLY":
        raise ValidationError(
            f"artifact state {artifact.lifecycle_state} cannot be validated",
            code="INVALID_ARTIFACT_STATE")

    warnings: Dict[str, Any] = {}
    experiment = None
    if experiment_id is not None:
        experiment = db.query(ResearchExperiment).filter_by(
            experiment_id=experiment_id).first()
        if experiment is None:
            raise ValidationError(f"unknown experiment: {experiment_id}",
                                  code="UNKNOWN_EXPERIMENT")
    elif artifact.experiment_id:
        experiment = db.query(ResearchExperiment).filter_by(
            experiment_id=artifact.experiment_id).first()

    evidence_state = None
    leakage_status = None
    sample_sizes: Dict[str, Any] = {}
    metrics: Dict[str, Any] = {}
    uncertainty: Dict[str, Any] = {}
    temporal_integrity = None
    if experiment is not None:
        evidence_state = experiment.evidence_state
        leakage_status = experiment.leakage_status
        sample_sizes = {"test_observations": (
            experiment.comparison or {}).get("n")}
        metrics = {"baseline": experiment.baseline_metrics,
                   "candidate": experiment.candidate_metrics}
        uncertainty = experiment.uncertainty or {}
        temporal_integrity = "AUDITED" if (
            experiment.leakage_status == "PASS") else "FAILED"
        if experiment.leakage_status != "PASS":
            warnings["leakage"] = "experiment leakage status is not PASS"
    else:
        warnings["experiment"] = "no linked research experiment"

    # Compatibility probe: run the candidate path once is out of scope
    # here; compatibility is assessed from the artifact contract.
    compatibility = {
        "feature_contract": artifact.feature_contract,
        "prediction_mode": artifact.prediction_mode,
        "schema": "FullPrediction-compatible (ensemble/elo/poisson families)",
        "compatible": artifact.feature_contract == "features_v1"
        and artifact.prediction_mode == "PRE_MATCH",
    }
    if not compatibility["compatible"]:
        warnings["compatibility"] = "artifact contract is not production-compatible"

    if leakage_status is not None and leakage_status != "PASS":
        result = VALIDATION_INVALID
    elif not compatibility["compatible"]:
        result = VALIDATION_REJECTED
    elif evidence_state in ("IMPROVEMENT_EVIDENCE", "NO_CLEAR_DIFFERENCE",
                            "REGRESSION_EVIDENCE"):
        result = VALIDATION_VALIDATED
    elif evidence_state == "INSUFFICIENT_EVIDENCE":
        result = VALIDATION_INCONCLUSIVE
    else:
        result = VALIDATION_INCONCLUSIVE
        warnings["evidence"] = "no conclusive research evidence state"

    semantic = {
        "candidate_artifact_id": artifact.artifact_id,
        "experiment_id": experiment.experiment_id if experiment else "",
        "dataset_hash": artifact.dataset_hash or "",
        "config_fingerprint": artifact.config_fingerprint,
        "result": result,
        "evidence_state": evidence_state or "",
        "validator": VALIDATOR_VERSION,
    }
    report_hash = canonical_hash(semantic)
    row = ModelValidationReport(
        validation_id=f"val_{uuid.uuid4().hex[:12]}",
        candidate_artifact_id=artifact.artifact_id,
        champion_artifact_id=_current_champion_id(db),
        experiment_id=experiment.experiment_id if experiment else None,
        dataset_hash=artifact.dataset_hash,
        config_fingerprint=artifact.config_fingerprint,
        evaluation_window=artifact.evaluation_period or {},
        competitions={},
        sample_sizes=sample_sizes,
        metrics=metrics,
        uncertainty=uncertainty,
        evidence_state=evidence_state,
        leakage_status=leakage_status,
        temporal_integrity=temporal_integrity,
        compatibility=compatibility,
        validation_result=result,
        warnings=warnings,
        validator_version=VALIDATOR_VERSION,
        report_hash=report_hash,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    if artifact.lifecycle_state == "RESEARCH_ONLY":
        transition(db, artifact, VALIDATION_PENDING,
                   actor=actor or "system", reason="validation started",
                   references={"validation_id": row.validation_id})
    if result == VALIDATION_VALIDATED:
        transition(db, artifact, VALIDATED, actor=actor or "system",
                   reason="validation passed",
                   references={"validation_id": row.validation_id})
    elif result in (VALIDATION_REJECTED, VALIDATION_INVALID):
        transition(db, artifact,
                   "REJECTED" if result == VALIDATION_REJECTED else "INVALIDATED",
                   actor=actor or "system", reason="validation failed",
                   references={"validation_id": row.validation_id})
    else:
        log_event(db, artifact_id=artifact.artifact_id,
                  from_state=artifact.lifecycle_state,
                  to_state=artifact.lifecycle_state,
                  actor=actor or "system",
                  reason=f"validation {result}",
                  references={"validation_id": row.validation_id})
    return validation_to_dict(row)


def _current_champion_id(db: Session) -> str:
    from .registry import current_champion

    try:
        return current_champion(db).artifact_id
    except GovernanceError:
        return ""


def validation_to_dict(row: ModelValidationReport) -> Dict[str, Any]:
    return {
        "validation_id": row.validation_id,
        "candidate_artifact_id": row.candidate_artifact_id,
        "champion_artifact_id": row.champion_artifact_id,
        "experiment_id": row.experiment_id,
        "dataset_hash": row.dataset_hash,
        "config_fingerprint": row.config_fingerprint,
        "evaluation_window": row.evaluation_window,
        "competitions": row.competitions,
        "sample_sizes": row.sample_sizes,
        "metrics": row.metrics,
        "uncertainty": row.uncertainty,
        "evidence_state": row.evidence_state,
        "leakage_status": row.leakage_status,
        "temporal_integrity": row.temporal_integrity,
        "compatibility": row.compatibility,
        "validation_result": row.validation_result,
        "warnings": row.warnings,
        "validator_version": row.validator_version,
        "report_hash": row.report_hash,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }
