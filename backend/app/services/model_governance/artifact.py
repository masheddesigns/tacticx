"""Phase 30 immutable model artifact identity + registry helpers."""
from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.db.models.governance import ModelArtifact

from .contracts import (
    CHAMPION_MEMBERS,
    CHAMPION_MODEL_ID,
    CHAMPION_MODEL_VERSION,
    CHAMPION_WEIGHTS,
    RESEARCH_ONLY,
    canonical_hash,
)
from .lifecycle import GovernanceError, log_event


def artifact_identity(
    *,
    model_id: str,
    model_version: str,
    members: List[str],
    weights: List[float],
    candidate_id: Optional[str] = None,
    experiment_id: Optional[str] = None,
    dataset_id: Optional[str] = None,
    dataset_hash: Optional[str] = None,
    feature_contract: str = "features_v1",
    prediction_mode: str = "PRE_MATCH",
    train_period: Optional[Dict[str, Any]] = None,
    evaluation_period: Optional[Dict[str, Any]] = None,
    code_hash: str = "",
) -> Dict[str, Any]:
    """Deterministic identity payload (weights included: version strings
    are weight-blind, so the fingerprint must carry them)."""
    return {
        "model_id": model_id,
        "model_version": model_version,
        "members": list(members),
        "weights": [round(float(w), 6) for w in weights],
        "candidate_id": candidate_id or "",
        "experiment_id": experiment_id or "",
        "dataset_id": dataset_id or "",
        "dataset_hash": dataset_hash or "",
        "feature_contract": feature_contract,
        "prediction_mode": prediction_mode,
        "train_period": train_period or {},
        "evaluation_period": evaluation_period or {},
        "code_hash": code_hash,
    }


def register_artifact(
    db: Session,
    *,
    model_id: str,
    model_version: str,
    members: List[str],
    weights: List[float],
    candidate_id: Optional[str] = None,
    experiment_id: Optional[str] = None,
    dataset_id: Optional[str] = None,
    dataset_hash: Optional[str] = None,
    feature_contract: str = "features_v1",
    prediction_mode: str = "PRE_MATCH",
    train_period: Optional[Dict[str, Any]] = None,
    evaluation_period: Optional[Dict[str, Any]] = None,
    code_hash: str = "",
    provenance: Optional[Dict[str, Any]] = None,
    initial_state: Optional[str] = None,
) -> ModelArtifact:
    """Create (or reuse by hash) an immutable artifact.

    initial_state is honored only at creation (champion seeding); every
    subsequent move goes through the transition validator.
    """
    identity = artifact_identity(
        model_id=model_id, model_version=model_version,
        members=members, weights=weights, candidate_id=candidate_id,
        experiment_id=experiment_id, dataset_id=dataset_id,
        dataset_hash=dataset_hash, feature_contract=feature_contract,
        prediction_mode=prediction_mode, train_period=train_period,
        evaluation_period=evaluation_period, code_hash=code_hash)
    artifact_hash = canonical_hash(identity)
    existing = db.query(ModelArtifact).filter_by(
        artifact_hash=artifact_hash).first()
    if existing is not None:
        return existing
    state = initial_state or RESEARCH_ONLY
    row = ModelArtifact(
        artifact_id=f"art_{uuid.uuid4().hex[:12]}",
        model_id=model_id,
        model_version=model_version,
        candidate_id=candidate_id,
        experiment_id=experiment_id,
        dataset_id=dataset_id,
        dataset_hash=dataset_hash,
        config_fingerprint={"members": list(members),
                            "weights": [round(float(w), 6)
                                        for w in weights]},
        feature_contract=feature_contract,
        prediction_mode=prediction_mode,
        train_period=train_period or {},
        evaluation_period=evaluation_period or {},
        code_hash=code_hash,
        lifecycle_state=state,
        artifact_hash=artifact_hash,
        provenance=provenance or {},
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    log_event(db, artifact_id=row.artifact_id, from_state="",
              to_state=state, actor="system",
              reason="artifact registered",
              references={"artifact_hash": artifact_hash})
    return row


def champion_artifact_identity() -> Dict[str, Any]:
    return artifact_identity(
        model_id=CHAMPION_MODEL_ID, model_version=CHAMPION_MODEL_VERSION,
        members=CHAMPION_MEMBERS, weights=CHAMPION_WEIGHTS)


def get_artifact(db: Session, artifact_id: str) -> ModelArtifact:
    row = db.query(ModelArtifact).filter_by(artifact_id=artifact_id).first()
    if row is None:
        raise GovernanceError(f"unknown artifact: {artifact_id}",
                              code="UNKNOWN_ARTIFACT")
    return row


def artifact_to_dict(row: ModelArtifact) -> Dict[str, Any]:
    return {
        "artifact_id": row.artifact_id,
        "model_id": row.model_id,
        "model_version": row.model_version,
        "candidate_id": row.candidate_id,
        "experiment_id": row.experiment_id,
        "dataset_id": row.dataset_id,
        "dataset_hash": row.dataset_hash,
        "config_fingerprint": row.config_fingerprint,
        "feature_contract": row.feature_contract,
        "prediction_mode": row.prediction_mode,
        "train_period": row.train_period,
        "evaluation_period": row.evaluation_period,
        "code_hash": row.code_hash,
        "lifecycle_state": row.lifecycle_state,
        "artifact_hash": row.artifact_hash,
        "provenance": row.provenance,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }
