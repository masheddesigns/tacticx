"""Production acquisition scheduler — append-only job records + database locks.

Models are append-only: every execution creates a new AcquisitionJobRecord.
Locks are short-lived rows with TTL-based expiry to survive process crashes.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, DateTime, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AcquisitionJobRecord(Base):
    """Append-only record of one scheduled job execution. Never overwritten."""

    __tablename__ = "acquisition_job_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[str] = mapped_column(String(128), index=True)
    job_type: Mapped[str] = mapped_column(String(64), index=True)
    source: Mapped[str] = mapped_column(String(64), default="", index=True)
    competition: Mapped[str] = mapped_column(String(32), default="", index=True)
    season: Mapped[str] = mapped_column(String(32), default="")
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    plan_hash: Mapped[str] = mapped_column(String(64), default="")
    qualification_hash: Mapped[str] = mapped_column(String(64), default="")
    request_count: Mapped[int] = mapped_column(Integer, default=0)
    success_count: Mapped[int] = mapped_column(Integer, default=0)
    failure_count: Mapped[int] = mapped_column(Integer, default=0)
    new_observations: Mapped[int] = mapped_column(Integer, default=0)
    duplicate_observations: Mapped[int] = mapped_column(Integer, default=0)
    new_matches: Mapped[int] = mapped_column(Integer, default=0)
    updated_matches: Mapped[int] = mapped_column(Integer, default=0)
    unresolved_identities: Mapped[int] = mapped_column(Integer, default=0)
    conflicts: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    error_code: Mapped[str] = mapped_column(String(128), default="")
    error_message: Mapped[str] = mapped_column(String(512), default="")
    dry_run: Mapped[bool] = mapped_column(Integer, default=0)
    trigger: Mapped[str] = mapped_column(String(32), default="scheduler")
    details: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    __table_args__ = (
        Index("ix_acq_job_records_type_status", "job_type", "status"),
        Index("ix_acq_job_records_competition", "competition", "job_type"),
    )


class AcquisitionJobLock(Base):
    """Short-lived lock row with TTL expiry. Survives process crashes via
    natural expiry. Never manually deleted — the stale-lock recovery
    reclaims expired locks automatically."""

    __tablename__ = "acquisition_job_locks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lock_key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    owner: Mapped[str] = mapped_column(String(128), default="")
    acquired_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    job_type: Mapped[str] = mapped_column(String(64), default="")
    competition: Mapped[str] = mapped_column(String(32), default="")
