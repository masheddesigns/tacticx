"""Phase 19 source qualification evidence table (append-only)."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SourceQualification(Base):
    """One append-only qualification evidence snapshot. Never stores
    secrets, credentials, or raw provider payloads."""

    __tablename__ = "source_qualifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    qualification_run_id: Mapped[str] = mapped_column(String(64), default="",
                                                      index=True)
    source: Mapped[str] = mapped_column(String(64), default="", index=True)
    competition: Mapped[str] = mapped_column(String(32), default="")
    season: Mapped[str] = mapped_column(String(16), default="")
    retrieved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())
    request_count: Mapped[int] = mapped_column(Integer, default=0)
    response_count: Mapped[int] = mapped_column(Integer, default=0)
    fixture_count: Mapped[int] = mapped_column(Integer, default=0)
    resolved_count: Mapped[int] = mapped_column(Integer, default=0)
    unresolved_count: Mapped[int] = mapped_column(Integer, default=0)
    conflict_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), default="unqualified",
                                        index=True)
    reason_codes: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    capability_hash: Mapped[str] = mapped_column(String(64), default="")
    sample_hash: Mapped[str] = mapped_column(String(64), default="")
