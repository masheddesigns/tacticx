"""Phase 27 prediction evaluation records.

Two append-only tables:

- MatchOutcomeSnapshot: canonical immutable final-result snapshot for one
  match. Verified := status FINISHED with recorded home/away scores.
- PredictionEvaluationRecord: immutable scoring of one Phase 26 prediction
  snapshot against one outcome snapshot. Content-addressed and idempotent
  on (prediction_id, outcome_hash).

CRITICAL INVARIANTS:
- Rows are never updated in place.
- A legitimately corrected canonical result creates a new outcome snapshot
  linked via supersedes_outcome_id, and a new evaluation version.
- Evaluation never mutates prediction snapshots (separate tables, no
  foreign-key cascade, read-only snapshot access).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MatchOutcomeSnapshot(Base):
    """Canonical immutable final result for one match."""

    __tablename__ = "match_outcome_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    outcome_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), index=True)
    final_home_goals: Mapped[int] = mapped_column(Integer)
    final_away_goals: Mapped[int] = mapped_column(Integer)
    final_result: Mapped[str] = mapped_column(String(16), index=True)
    status: Mapped[str] = mapped_column(String(16), default="FINISHED")
    outcome_timestamp: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True)
    provider: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    provider_match_id: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True)
    provenance: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    outcome_hash: Mapped[str] = mapped_column(String(64), index=True)
    supersedes_outcome_id: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    __table_args__ = (
        Index("ix_outcome_match_hash", "match_id", "outcome_hash", unique=True),
    )


class PredictionEvaluationRecord(Base):
    """Immutable scoring of one prediction snapshot against one outcome."""

    __tablename__ = "prediction_evaluation_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    evaluation_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    prediction_id: Mapped[str] = mapped_column(String(64), index=True)
    prediction_hash: Mapped[str] = mapped_column(String(64))
    outcome_snapshot_id: Mapped[str] = mapped_column(String(64), index=True)
    outcome_hash: Mapped[str] = mapped_column(String(64))
    model_id: Mapped[str] = mapped_column(String(64), index=True)
    model_version: Mapped[str] = mapped_column(String(64), index=True)
    prediction_mode: Mapped[str] = mapped_column(String(32), default="PRE_MATCH")
    competition: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)
    season: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)
    prediction_cutoff: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True)
    kickoff_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True)
    actual_result: Mapped[str] = mapped_column(String(16))
    actual_home_goals: Mapped[int] = mapped_column(Integer)
    actual_away_goals: Mapped[int] = mapped_column(Integer)
    metrics: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    evaluation_version: Mapped[int] = mapped_column(Integer, default=1)
    evaluation_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    evaluation_hash: Mapped[str] = mapped_column(String(64), unique=True)
    provenance: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    __table_args__ = (
        Index("ix_eval_match_created", "prediction_id", "created_at"),
        Index("ix_eval_model_version", "model_id", "model_version"),
        Index("ix_eval_competition_season", "competition", "season"),
    )
