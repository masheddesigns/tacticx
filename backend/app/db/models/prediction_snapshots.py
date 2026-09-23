"""Pre-match prediction execution snapshots (Phase 26).

Two append-only tables:

- PredictionFeatureSnapshot: deterministic cutoff-safe feature payload used
  as model input. Content-addressed by snapshot_hash.
- PreMatchPredictionSnapshot: immutable validated model output bound to the
  exact Phase 25.1 readiness certificate and feature snapshot that produced it.

CRITICAL INVARIANTS:
- Rows are never updated in place.
- A new cutoff / model version / feature payload creates a new row.
- Repeated execution with identical material inputs returns the existing row
  (DB unique constraint on execution_key enforces idempotency).
- prediction_hash covers every material input; nondeterministic timestamps
  are excluded from the hashed payload.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PredictionFeatureSnapshot(Base):
    """Deterministic cutoff-safe feature payload for one (match, cutoff)."""

    __tablename__ = "prediction_feature_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    snapshot_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), index=True)
    cutoff: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    feature_version: Mapped[str] = mapped_column(String(32), default="features_v1")
    model_id: Mapped[str] = mapped_column(String(64))
    model_version: Mapped[str] = mapped_column(String(64))
    features: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    provenance: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    snapshot_hash: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    __table_args__ = (
        Index("ix_pred_feat_match_hash", "match_id", "snapshot_hash", unique=True),
    )


class PreMatchPredictionSnapshot(Base):
    """Immutable validated pre-match prediction bound to readiness + features."""

    __tablename__ = "prematch_prediction_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    prediction_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), index=True)
    prediction_version: Mapped[int] = mapped_column(Integer, default=1)
    model_id: Mapped[str] = mapped_column(String(64), index=True)
    model_version: Mapped[str] = mapped_column(String(64), index=True)
    prediction_mode: Mapped[str] = mapped_column(String(32), default="PRE_MATCH")
    cutoff_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    kickoff_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Readiness binding (Phase 25.1 certificate)
    readiness_certificate_id: Mapped[str] = mapped_column(String(64), index=True)
    readiness_certificate_hash: Mapped[str] = mapped_column(String(64))
    readiness_state: Mapped[str] = mapped_column(String(32), index=True)
    # Feature binding
    feature_snapshot_id: Mapped[str] = mapped_column(String(64), index=True)
    feature_snapshot_hash: Mapped[str] = mapped_column(String(64))
    # Payload + integrity
    prediction_payload: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    prediction_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    # Deterministic idempotency key over all material inputs
    execution_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    provenance: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    __table_args__ = (
        Index("ix_prematch_pred_match_created", "match_id", "created_at"),
        Index("ix_prematch_pred_model_version", "model_id", "model_version"),
    )
