"""Phase 30 model governance records (immutable, append-only).

Tables:
- ModelArtifact: immutable candidate/champion identity (weights included).
- ModelRegistry: champion/challenger role bindings per scope.
- ModelValidationReport: immutable validation decisions.
- ModelPromotionRequest: explicit promotion requests (never self-activating).
- ModelApprovalRecord: explicit human decisions (append-only).
- ModelGovernanceEvent: append-only lifecycle event log.
- ShadowPredictionSnapshot: isolated challenger-vs-champion outputs.

CRITICAL INVARIANTS:
- No foreign keys into production tables; linkage by id/hash strings.
- Validation reports, approvals, and events are never updated.
- The champion binding changes only through explicit activation/rollback
  with optimistic concurrency (expected champion match).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import JSON, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ModelArtifact(Base):
    __tablename__ = "model_artifacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    artifact_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    model_id: Mapped[str] = mapped_column(String(64), index=True)
    model_version: Mapped[str] = mapped_column(String(64), index=True)
    candidate_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    experiment_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    dataset_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    dataset_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    config_fingerprint: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    feature_contract: Mapped[str] = mapped_column(String(32), default="features_v1")
    prediction_mode: Mapped[str] = mapped_column(String(32), default="PRE_MATCH")
    train_period: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    evaluation_period: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    code_hash: Mapped[str] = mapped_column(String(64), default="")
    lifecycle_state: Mapped[str] = mapped_column(
        String(32), default="RESEARCH_ONLY", index=True)
    artifact_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    provenance: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class ModelRegistry(Base):
    __tablename__ = "model_registry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    role: Mapped[str] = mapped_column(String(32), index=True)
    competition: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    season: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    prediction_mode: Mapped[str] = mapped_column(String(32), default="PRE_MATCH")
    artifact_id: Mapped[str] = mapped_column(String(64), index=True)
    state: Mapped[str] = mapped_column(String(32), default="ACTIVE")
    supersedes_registry_id: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class ModelValidationReport(Base):
    __tablename__ = "model_validation_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    validation_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    candidate_artifact_id: Mapped[str] = mapped_column(String(64), index=True)
    champion_artifact_id: Mapped[str] = mapped_column(String(64))
    experiment_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    dataset_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    config_fingerprint: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    evaluation_window: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    competitions: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    sample_sizes: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    metrics: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    uncertainty: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    evidence_state: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    leakage_status: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    temporal_integrity: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    compatibility: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    validation_result: Mapped[str] = mapped_column(String(32), index=True)
    warnings: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    validator_version: Mapped[str] = mapped_column(String(32), default="v1")
    report_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class ModelPromotionRequest(Base):
    __tablename__ = "model_promotion_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    candidate_artifact_id: Mapped[str] = mapped_column(String(64), index=True)
    validation_id: Mapped[str] = mapped_column(String(64))
    champion_artifact_id: Mapped[str] = mapped_column(String(64))
    competition: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    season: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    prediction_mode: Mapped[str] = mapped_column(String(32), default="PRE_MATCH")
    deployment_mode: Mapped[str] = mapped_column(String(32), default="SHADOW")
    requester: Mapped[str] = mapped_column(String(128), default="")
    reason: Mapped[str] = mapped_column(String(1024), default="")
    state: Mapped[str] = mapped_column(String(32), default="OPEN", index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class ModelApprovalRecord(Base):
    __tablename__ = "model_approval_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    approval_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    request_id: Mapped[str] = mapped_column(String(64), index=True)
    decision: Mapped[str] = mapped_column(String(16), index=True)
    actor: Mapped[str] = mapped_column(String(128), default="")
    reason: Mapped[str] = mapped_column(String(1024), default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class ModelGovernanceEvent(Base):
    __tablename__ = "model_governance_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    artifact_id: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, index=True)
    from_state: Mapped[str] = mapped_column(String(32), default="")
    to_state: Mapped[str] = mapped_column(String(32), default="")
    actor: Mapped[str] = mapped_column(String(128), default="")
    reason: Mapped[str] = mapped_column(String(1024), default="")
    references: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class ShadowPredictionSnapshot(Base):
    __tablename__ = "shadow_prediction_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    shadow_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    match_id: Mapped[int] = mapped_column(Integer, index=True)
    challenger_artifact_id: Mapped[str] = mapped_column(String(64), index=True)
    champion_artifact_id: Mapped[str] = mapped_column(String(64), index=True)
    cutoff: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    feature_snapshot_hash: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True)
    # Phase 32 shared-input bindings (immutable once written).
    feature_snapshot_id: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, index=True)
    production_prediction_id: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, index=True)
    shadow_execution_key: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, unique=True, index=True)
    evaluation_state: Mapped[str] = mapped_column(String(32), default="PENDING")
    champion_output: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    challenger_output: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    champion_output_hash: Mapped[str] = mapped_column(String(64), default="")
    challenger_output_hash: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class ShadowEvaluationRecord(Base):
    """Immutable challenger-vs-champion scoring for one shadow pair.

    Champion metrics mirror the linked Phase 27 evaluation; challenger
    metrics use the same scoring implementation against the shared
    outcome snapshot. Factual differences only — no winner declaration.
    """

    __tablename__ = "shadow_evaluation_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    evaluation_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    shadow_id: Mapped[str] = mapped_column(String(64), index=True)
    match_id: Mapped[int] = mapped_column(Integer, index=True)
    challenger_artifact_id: Mapped[str] = mapped_column(String(64), index=True)
    champion_artifact_id: Mapped[str] = mapped_column(String(64), index=True)
    outcome_snapshot_id: Mapped[str] = mapped_column(String(64))
    outcome_hash: Mapped[str] = mapped_column(String(64))
    champion_metrics: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    challenger_metrics: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    differences: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    sample_note: Mapped[str] = mapped_column(String(256), default="")
    evaluation_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
