"""Phase 15 intelligence snapshot table (immutable, hashed)."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class IntelligenceSnapshot(Base):
    """One immutable intelligence output with full provenance + hash."""

    __tablename__ = "intelligence_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    snapshot_id: Mapped[str] = mapped_column(String(64), index=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), index=True)
    prediction_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("predictions.id"), nullable=True)
    model_version: Mapped[str] = mapped_column(String(64), default="")
    feature_version: Mapped[str] = mapped_column(String(32), default="features_v1")
    dataset_version: Mapped[str] = mapped_column(String(64), default="")
    market_snapshot_version: Mapped[str] = mapped_column(String(64), default="")
    cutoff: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True)
    payload: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    payload_hash: Mapped[str] = mapped_column(String(64), default="", index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())
