"""Phase 16 MiroFish scenario-run table (append-only)."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MiroFishScenarioRun(Base):
    """One immutable MiroFish execution. History is never overwritten;
    identical requests may share hashes but each execution appends a row."""

    __tablename__ = "mirofish_scenario_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), index=True)
    intelligence_snapshot_id: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, index=True)
    contract_version: Mapped[str] = mapped_column(String(64), default="")
    scenario_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    scenario_hash: Mapped[str] = mapped_column(String(64), default="")
    request_hash: Mapped[str] = mapped_column(String(64), default="", index=True)
    response_hash: Mapped[str] = mapped_column(String(64), default="")
    provider: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(32), default="unavailable", index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True)
    result_payload: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    error_code: Mapped[str] = mapped_column(String(64), default="")
