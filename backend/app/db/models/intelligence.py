"""Phase 6 analytical artifact tables.

Every stored artifact records prediction_id, model_version, feature_version,
cutoff, calculation_version, input_reference and status — the same audit
columns Phase 5 demanded of run artifacts. Tables are created via
Base.metadata (the project's established create_all pattern); no migration
files are needed. Stored analytical artifacts never mutate the core
Prediction row they reference.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PredictionExplanation(Base):
    __tablename__ = "prediction_explanations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    prediction_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("predictions.id"), nullable=True, index=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), index=True)
    model_name: Mapped[str] = mapped_column(String(64), default="")
    model_version: Mapped[str] = mapped_column(String(64), default="")
    feature_version: Mapped[str] = mapped_column(String(32), default="features_v1")
    cutoff: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    temporal_mode: Mapped[str] = mapped_column(String(32), default="strict_prematch")
    calculation_version: Mapped[str] = mapped_column(String(64), default="composer_v1")
    input_reference: Mapped[str] = mapped_column(String(128), default="")
    status: Mapped[str] = mapped_column(String(32), default="ok", index=True)
    payload: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())


class ScenarioRun(Base):
    __tablename__ = "scenario_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    prediction_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("predictions.id"), nullable=True, index=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), index=True)
    model_name: Mapped[str] = mapped_column(String(64), default="")
    model_version: Mapped[str] = mapped_column(String(64), default="")
    feature_version: Mapped[str] = mapped_column(String(32), default="features_v1")
    cutoff: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    temporal_mode: Mapped[str] = mapped_column(String(32), default="strict_prematch")
    calculation_version: Mapped[str] = mapped_column(String(64), default="scenarios_v1")
    input_reference: Mapped[str] = mapped_column(String(128), default="")
    status: Mapped[str] = mapped_column(String(32), default="ok", index=True)
    payload: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())


class AnalogueResult(Base):
    __tablename__ = "analogue_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    prediction_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("predictions.id"), nullable=True, index=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), index=True)
    model_version: Mapped[str] = mapped_column(String(64), default="")
    feature_version: Mapped[str] = mapped_column(String(32), default="features_v1")
    cutoff: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    temporal_mode: Mapped[str] = mapped_column(String(32), default="strict_prematch")
    calculation_version: Mapped[str] = mapped_column(String(64), default="analogues_v1")
    input_reference: Mapped[str] = mapped_column(String(128), default="")
    status: Mapped[str] = mapped_column(String(32), default="ok", index=True)
    payload: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())


class MiroFishRun(Base):
    __tablename__ = "mirofish_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    prediction_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("predictions.id"), nullable=True, index=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), index=True)
    model_version: Mapped[str] = mapped_column(String(64), default="")
    feature_version: Mapped[str] = mapped_column(String(32), default="features_v1")
    cutoff: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    temporal_mode: Mapped[str] = mapped_column(String(32), default="strict_prematch")
    calculation_version: Mapped[str] = mapped_column(String(64), default="mirofish_adapter_v1")
    input_reference: Mapped[str] = mapped_column(String(128), default="")
    status: Mapped[str] = mapped_column(String(32), default="unavailable", index=True)
    scenario_seed: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    mirofish_version: Mapped[str] = mapped_column(String(64), default="")
    payload: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())
