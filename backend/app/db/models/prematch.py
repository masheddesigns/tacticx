"""Pre-match readiness certificate database models (Phase 25).

Provides an immutable audit record for each evaluated match prior to prediction execution.
Contract version: PREMATCH_CERTIFICATE_V1.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PreMatchReadinessCertificate(Base):
    """Immutable audit certificate generated for a match at an evaluation cutoff.

    CRITICAL INVARIANTS:
    - Never overwritten in-place.
    - Post-cutoff data changes do not mutate an existing certificate.
    - Subsequent evaluations or reconciliations produce a new certificate referencing
      supersedes_certificate_id.
    """

    __tablename__ = "prematch_readiness_certificates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    certificate_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    certificate_version: Mapped[str] = mapped_column(String(32), default="PREMATCH_CERTIFICATE_V1")
    readiness_contract_version: Mapped[str] = mapped_column(String(32), default="PREMATCH_CERTIFICATE_V1")

    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), index=True)
    competition: Mapped[str] = mapped_column(String(32), index=True)
    season: Mapped[str] = mapped_column(String(32), index=True)
    home_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    away_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))

    kickoff_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    cutoff: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    readiness_state: Mapped[str] = mapped_column(String(32), index=True)  # PREDICTION_READY | READY_DEGRADED | BLOCKED
    gate_verdicts: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    blocking_reasons: Mapped[List[str]] = mapped_column(JSON, default=list)
    warnings: Mapped[List[str]] = mapped_column(JSON, default=list)
    payload_hash: Mapped[str] = mapped_column(String(64), index=True)  # SHA-256 of canonical payload
    supersedes_certificate_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    __table_args__ = (
        Index("ix_prematch_cert_match_created", "match_id", "created_at"),
        Index("ix_prematch_cert_season_state", "season", "readiness_state"),
    )
