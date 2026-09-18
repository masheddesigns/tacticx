"""Phase 12 research model registry table."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ResearchModel(Base):
    """One research candidate with windows, params, metrics, artifact hash."""

    __tablename__ = "research_models"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    model_id: Mapped[str] = mapped_column(String(64), index=True)
    model_version: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(32), default="research", index=True)
    feature_version: Mapped[str] = mapped_column(String(32), default="")
    dataset_version: Mapped[str] = mapped_column(String(64), default="")
    training_period: Mapped[str] = mapped_column(String(64), default="")
    validation_period: Mapped[str] = mapped_column(String(64), default="")
    test_period: Mapped[str] = mapped_column(String(64), default="")
    parameters: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    metrics: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    artifact_hash: Mapped[str] = mapped_column(String(64), default="", index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())
