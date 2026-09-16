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


class PredictionResult(Base):
    __tablename__ = "prediction_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    prediction_id: Mapped[int] = mapped_column(ForeignKey("predictions.id"), index=True)
    actual_result: Mapped[str] = mapped_column(String(64))
    resolved_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
