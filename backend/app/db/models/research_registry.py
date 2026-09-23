"""Phase 29 controlled research registry (immutable, append-only).

Three tables:
- ResearchCandidate: registered hypothesis with declared inputs.
- ResearchDataset: versioned observation sets with provenance + hash.
- ResearchExperiment: immutable completed-run record with comparison.

CRITICAL INVARIANTS:
- Research rows never reference production tables by foreign key;
  linkage is by immutable id/hash strings (read-only against prod).
- No status value promotes to production; promotion is out of scope.
- Rows are never updated; supersession creates new rows.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import JSON, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ResearchCandidate(Base):
    """One registered research hypothesis."""

    __tablename__ = "research_candidates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    candidate_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    version: Mapped[str] = mapped_column(String(32), default="v1")
    description: Mapped[str] = mapped_column(String(1024), default="")
    hypothesis: Mapped[str] = mapped_column(String(1024), default="")
    feature_set: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    model_family: Mapped[str] = mapped_column(String(64), default="")
    hyperparameters: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    declared_inputs: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    code_hash: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(32), default="DRAFT", index=True)
    supersedes_candidate_id: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class ResearchDataset(Base):
    """One versioned research observation set."""

    __tablename__ = "research_datasets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dataset_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    dataset_version: Mapped[str] = mapped_column(String(32), default="v1")
    competitions: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    seasons: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    feature_version: Mapped[str] = mapped_column(String(32), default="features_v1")
    cutoff_policy: Mapped[str] = mapped_column(String(64), default="")
    inclusion_rules: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    observations: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    train_period: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    validation_period: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    test_period: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    provenance: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    dataset_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class ResearchExperiment(Base):
    """One immutable completed experiment run."""

    __tablename__ = "research_experiments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    experiment_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    candidate_id: Mapped[str] = mapped_column(String(64), index=True)
    candidate_version: Mapped[str] = mapped_column(String(32), default="")
    dataset_id: Mapped[str] = mapped_column(String(64), index=True)
    dataset_hash: Mapped[str] = mapped_column(String(64))
    baseline_model_id: Mapped[str] = mapped_column(String(64), default="")
    baseline_model_version: Mapped[str] = mapped_column(String(64), default="")
    evaluation_protocol: Mapped[str] = mapped_column(String(64), default="")
    evaluation_protocol_version: Mapped[str] = mapped_column(
        String(32), default="v1")
    random_seed: Mapped[int] = mapped_column(Integer, default=7)
    baseline_metrics: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    candidate_metrics: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    comparison: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    uncertainty: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    calibration: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    leakage_status: Mapped[str] = mapped_column(String(32), default="PASS")
    evidence_state: Mapped[str] = mapped_column(String(32), default="")
    reproducibility: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    execution_metadata: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    result_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
