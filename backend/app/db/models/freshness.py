"""Phase 10 fixture observation history (append-only)."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MatchObservation(Base):
    """One immutable source observation of a canonical match's fixture data.

    Kickoff/status/venue changes append new rows; old rows are never mutated.
    Each row retains observed_at, source, raw reference, previous and new
    values — postponements and reschedulings stay fully auditable.
    """

    __tablename__ = "match_observations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), index=True)
    source: Mapped[str] = mapped_column(String(64), default="", index=True)
    raw_reference: Mapped[str] = mapped_column(String(128), default="")
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())
    field: Mapped[str] = mapped_column(String(64), default="")
    previous_value: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    new_value: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    effective_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True)
    retrieved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True)
    payload: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    __table_args__ = (
        Index("ix_match_obs_match_field", "match_id", "field"),
    )
