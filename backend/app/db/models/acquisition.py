"""Phase 11 acquisition tables (append-only run log + activation + jobs)."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AcquisitionRun(Base):
    """Append-only record of one acquisition execution. Never stores payloads
    beyond counts, and never credentials."""

    __tablename__ = "acquisition_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    source: Mapped[str] = mapped_column(String(64), default="", index=True)
    job: Mapped[str] = mapped_column(String(64), default="")
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="running", index=True)
    requested_scope: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    records_seen: Mapped[int] = mapped_column(Integer, default=0)
    records_created: Mapped[int] = mapped_column(Integer, default=0)
    records_updated: Mapped[int] = mapped_column(Integer, default=0)
    records_rejected: Mapped[int] = mapped_column(Integer, default=0)
    records_quarantined: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    __table_args__ = (
        Index("ix_acq_runs_source_started", "source", "started_at"),
    )


class SourceActivation(Base):
    """Activation gate decisions: candidate → validated → active, with
    degraded/disabled states. The decision record is the audit trail."""

    __tablename__ = "source_activations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(64), index=True)
    state: Mapped[str] = mapped_column(String(32), default="candidate", index=True)
    decided_by: Mapped[str] = mapped_column(String(64), default="validation-gate")
    checks: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    reason: Mapped[str] = mapped_column(String(512), default="")
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())


class AcquisitionJob(Base):
    """Scheduling abstraction (scope/source/priority/last/next run).
    The actual scheduler stays outside this phase; this is the job registry."""

    __tablename__ = "acquisition_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    scope: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    source: Mapped[str] = mapped_column(String(64), default="")
    priority: Mapped[int] = mapped_column(Integer, default=100)
    last_run: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True)
    next_run: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True)
