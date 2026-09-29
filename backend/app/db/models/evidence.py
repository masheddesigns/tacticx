"""Phase 33 real-world performance evidence records (immutable).

- EvidenceCohort: deterministic paired-observation population definition.
- EvidenceSnapshot: immutable computed result over a cohort (versioned;
  recalculation creates a new row, never rewrites).

CRITICAL INVARIANTS:
- Linkage to production/research rows by id/hash strings only (no FKs
  into mutable-or-governed tables beyond plain integer match refs).
- Snapshot hash covers all material inputs; reruns return the existing
  row instead of duplicating.
- Evidence never authorizes governance transitions (no code path here
  touches the model registry).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import JSON, DateTime, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EvidenceCohort(Base):
    __tablename__ = "evidence_cohorts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cohort_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    champion_artifact_id: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True)
    challenger_artifact_id: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True)
    competitions: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    seasons: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    date_from: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True)
    date_to: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True)
    prediction_mode: Mapped[str] = mapped_column(String(32), default="PRE_MATCH")
    min_completeness: Mapped[float] = mapped_column(
        Float, default=1.0)  # reserved: required paired fraction
    query_fingerprint: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    cohort_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class EvidenceSnapshot(Base):
    __tablename__ = "evidence_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    snapshot_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    cohort_id: Mapped[str] = mapped_column(String(64), index=True)
    cohort_hash: Mapped[str] = mapped_column(String(64))
    calculation_version: Mapped[str] = mapped_column(
        String(32), default="evidence_calc_v1")
    observation_count: Mapped[int] = mapped_column(Integer, default=0)
    paired_count: Mapped[int] = mapped_column(Integer, default=0)
    excluded_count: Mapped[int] = mapped_column(Integer, default=0)
    observation_ids: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    champion_metrics: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    challenger_metrics: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    differences: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    uncertainty: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    calibration: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    data_quality: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    temporal_audit: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    evidence_state: Mapped[str] = mapped_column(String(32), index=True)
    snapshot_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
