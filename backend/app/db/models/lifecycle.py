"""Phase 7 prediction-lifecycle tables.

Prediction rows stay immutable; all lifecycle state (versioning, lock,
evaluation, health) lives here with full audit columns. Created via the
project's established Base.metadata.create_all pattern.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PredictionVersion(Base):
    """One immutable version in a prediction's lifecycle.

    States: generated -> refreshed -> ... -> locked -> evaluated.
    Superseded versions are never mutated; only their state advances.
    """

    __tablename__ = "prediction_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    prediction_id: Mapped[int] = mapped_column(ForeignKey("predictions.id"), index=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), index=True)
    version_number: Mapped[int] = mapped_column(Integer, default=1)
    state: Mapped[str] = mapped_column(String(32), default="generated", index=True)
    model_version: Mapped[str] = mapped_column(String(64), default="")
    feature_version: Mapped[str] = mapped_column(String(32), default="features_v1")
    calibration_version: Mapped[str] = mapped_column(String(64), default="none")
    scenario_version: Mapped[str] = mapped_column(String(64), default="none")
    derived_market_version: Mapped[str] = mapped_column(String(64), default="composer_v1")
    cutoff: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    market_snapshot_ids: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    feature_snapshot_ref: Mapped[str] = mapped_column(String(128), default="")
    input_reference: Mapped[str] = mapped_column(String(128), default="")
    status: Mapped[str] = mapped_column(String(32), default="ok")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_prediction_versions_match_created", "match_id", "created_at"),
        Index("ix_prediction_versions_match_cutoff", "match_id", "cutoff"),
    )


class PredictionDiff(Base):
    """Stored v(n)->v(n+1) difference. Neutral wording only."""

    __tablename__ = "prediction_diffs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), index=True)
    from_version_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("prediction_versions.id"), nullable=True)
    to_version_id: Mapped[int] = mapped_column(ForeignKey("prediction_versions.id"))
    payload: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())


class SourceHealth(Base):
    """Per-source operational health. Never stores secrets."""

    __tablename__ = "source_health"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    state: Mapped[str] = mapped_column(String(32), default="unknown", index=True)
    last_success: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True)
    last_failure: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True)
    failure_count: Mapped[int] = mapped_column(Integer, default=0)
    records_received: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    quota_remaining: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    last_error: Mapped[str] = mapped_column(String(512), default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())

    __table_args__ = (Index("ix_source_health_source_fetched", "source", "updated_at"),)


class PredictionEvaluation(Base):
    """Post-match evaluation record. Never mutates the prediction."""

    __tablename__ = "prediction_evaluations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    prediction_id: Mapped[int] = mapped_column(
        ForeignKey("predictions.id"), unique=True, index=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), index=True)
    actual_home_goals: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    actual_away_goals: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    actual_result: Mapped[str] = mapped_column(String(16), default="")
    metrics: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    evaluated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())
