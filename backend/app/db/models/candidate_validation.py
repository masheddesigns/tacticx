"""Phase 34 candidate validation reports (immutable, append-only).

A report binds: candidate artifact + champion artifact + Phase 33
evidence snapshot + versioned validation configuration. It records a
validation state for human governance review — never a promotion.

CRITICAL INVARIANTS:
- Rows are never updated; a new run creates a new row.
- Validation hash covers all material inputs (deterministic rerun).
- No code path here writes promotions, approvals, activations,
  rollbacks, predictions, outcomes, evaluations, or evidence.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import JSON, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CandidateValidationReport(Base):
    __tablename__ = "candidate_validation_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    validation_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    candidate_artifact_id: Mapped[str] = mapped_column(String(64), index=True)
    champion_artifact_id: Mapped[str] = mapped_column(String(64), index=True)
    evidence_snapshot_id: Mapped[str] = mapped_column(String(64), index=True)
    evidence_snapshot_hash: Mapped[str] = mapped_column(String(64))
    validation_config_id: Mapped[str] = mapped_column(String(32))
    validation_config_version: Mapped[str] = mapped_column(String(32))
    validation_state: Mapped[str] = mapped_column(String(32), index=True)
    evidence_state: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    rule_results: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    performance_summary: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    uncertainty_summary: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    data_quality_summary: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    temporal_summary: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    compatibility_summary: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    operational_summary: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    blocking_reasons: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    warnings: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    validation_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
