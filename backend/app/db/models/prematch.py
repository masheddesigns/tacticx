"""Pre-match readiness certificate database models (Phase 25 / Phase 25.1).

Provides an immutable audit record for each evaluated match prior to prediction execution.
Contract version: PREMATCH_CERTIFICATE_V1.

Phase 25.1 additions:
- provider, provider_match_id: explicit provider identity at cert generation time
- activation_state: derived from Phase 24 activation system (provider × competition × season)
- provider_qualification_version: null — SourceQualification has no version field
- prediction_config: full PredictionReadinessConfig dict
- model_version, prediction_mode: from selected model config
- required_features, available_features, missing_required_features, missing_optional_features
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
    - provider_qualification_version is always None because SourceQualification has
      no version field in Phase 24. Do not fabricate a version string here.
    """

    __tablename__ = "prematch_readiness_certificates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    certificate_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    certificate_version: Mapped[str] = mapped_column(String(32), default="PREMATCH_CERTIFICATE_V1")
    readiness_contract_version: Mapped[str] = mapped_column(String(32), default="PREMATCH_CERTIFICATE_V1")

    # Match identity
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), index=True)
    competition: Mapped[str] = mapped_column(String(32), index=True)
    season: Mapped[str] = mapped_column(String(32), index=True)
    home_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    away_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))

    # Temporal envelope
    kickoff_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    cutoff: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    # Readiness verdict
    readiness_state: Mapped[str] = mapped_column(String(32), index=True)  # PREDICTION_READY | READY_DEGRADED | BLOCKED
    gate_verdicts: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    blocking_reasons: Mapped[List[str]] = mapped_column(JSON, default=list)
    warnings: Mapped[List[str]] = mapped_column(JSON, default=list)

    # Payload integrity
    payload_hash: Mapped[str] = mapped_column(String(64), index=True)  # SHA-256 of canonical payload
    supersedes_certificate_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # Phase 25.1: Provider provenance
    provider: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    provider_match_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    activation_state: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    # Always None — SourceQualification has no version field in Phase 24
    provider_qualification_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # Phase 25.1: Prediction config snapshot
    prediction_config: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    model_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    prediction_mode: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    required_features: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    available_features: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    missing_required_features: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    missing_optional_features: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)

    # Audit
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    __table_args__ = (
        Index("ix_prematch_cert_match_created", "match_id", "created_at"),
        Index("ix_prematch_cert_season_state", "season", "readiness_state"),
    )
