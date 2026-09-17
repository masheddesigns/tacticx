"""Prediction + backtesting tables. Predictions are immutable once written."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Prediction(Base):
    __tablename__ = "predictions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), index=True)
    prediction_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    model_version: Mapped[str] = mapped_column(String(64), default="stub-0.1")
    prediction_type: Mapped[str] = mapped_column(String(64), default="1x2")
    predicted_probability: Mapped[float] = mapped_column(Float)
    # Full probability vector + confidence live here; input_snapshot enables
    # "what did the model know at prediction time?" reconstruction.
    probabilities: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    input_snapshot: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    # Phase 2 audit columns (all optional/nullable-safe for old rows).
    model_name: Mapped[str] = mapped_column(String(64), default="", index=True)
    prediction_cutoff: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    temporal_mode: Mapped[str] = mapped_column(String(32), default="strict_prematch")
    status: Mapped[str] = mapped_column(String(32), default="valid", index=True)
    feature_availability: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    model_config: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    random_seed: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)


class PredictionResult(Base):
    __tablename__ = "prediction_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    prediction_id: Mapped[int] = mapped_column(ForeignKey("predictions.id"), index=True)
    actual_result: Mapped[str] = mapped_column(String(64))
    resolved_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BacktestRun(Base):
    """One recorded backtest execution with its aggregate metrics."""

    __tablename__ = "backtest_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    model_name: Mapped[str] = mapped_column(String(64), default="", index=True)
    model_version: Mapped[str] = mapped_column(String(64), default="")
    league: Mapped[str] = mapped_column(String(32), default="")
    season: Mapped[str] = mapped_column(String(16), default="")
    temporal_mode: Mapped[str] = mapped_column(String(32), default="strict_prematch")
    date_from: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    date_to: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    sample_size: Mapped[int] = mapped_column(Integer, default=0)
    excluded_insufficient: Mapped[int] = mapped_column(Integer, default=0)
    excluded_temporal: Mapped[int] = mapped_column(Integer, default=0)
    metrics: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    model_config: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ModelTrainingRun(Base):
    """One fitted model artifact: config, windows, metrics, parameters.

    Parameters (coefficients, scaler stats, calibration temperature) are
    stored so any prediction citing this run is reproducible.
    """

    __tablename__ = "model_training_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    model_name: Mapped[str] = mapped_column(String(64), default="", index=True)
    model_version: Mapped[str] = mapped_column(String(64), default="")
    feature_version: Mapped[str] = mapped_column(String(32), default="features_v1")
    league: Mapped[str] = mapped_column(String(32), default="")
    train_from: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    train_to: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    train_sample: Mapped[int] = mapped_column(Integer, default=0)
    train_dropped: Mapped[int] = mapped_column(Integer, default=0)
    temporal_mode: Mapped[str] = mapped_column(String(32), default="strict_prematch")
    config: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    metrics: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    params: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ModelEvaluation(Base):
    """Evaluation of one (model version, training run) on one window."""

    __tablename__ = "model_evaluations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    training_run_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("model_training_runs.id"), nullable=True, index=True)
    model_name: Mapped[str] = mapped_column(String(64), default="", index=True)
    model_version: Mapped[str] = mapped_column(String(64), default="")
    league: Mapped[str] = mapped_column(String(32), default="")
    season: Mapped[str] = mapped_column(String(16), default="")
    date_from: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    date_to: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    temporal_mode: Mapped[str] = mapped_column(String(32), default="strict_prematch")
    sample_size: Mapped[int] = mapped_column(Integer, default=0)
    metrics: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
