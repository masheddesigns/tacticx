"""Source-agnostic provenance tables (Phase 1.6).

- team_provider_mappings: deterministic team identity across sources
- match_source_mappings: source-native match IDs -> canonical matches
- raw_data_records: every ingested record traceable to its source payload
- source_conflicts: disagreements between sources, flagged not overwritten
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TeamProviderMapping(Base):
    __tablename__ = "team_provider_mappings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)
    source: Mapped[str] = mapped_column(String(32), index=True)
    provider_team_id: Mapped[str] = mapped_column(String(64), default="")
    provider_team_name: Mapped[str] = mapped_column(String(128), default="")
    normalized_name: Mapped[str] = mapped_column(String(128), index=True)
    country: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    league: Mapped[str] = mapped_column(String(32), default="")
    resolution_method: Mapped[str] = mapped_column(String(32), default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("source", "provider_team_id", name="uq_team_mapping_source"),
    )


class PlayerProviderMapping(Base):
    """Deterministic player identity across sources (mirrors team mappings).

    Priority: provider player ID -> explicit mapping -> normalized identity
    (exactly one candidate) -> explicit alias -> unresolved. No fuzzy matching.
    """

    __tablename__ = "player_provider_mappings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), index=True)
    team_id: Mapped[Optional[int]] = mapped_column(ForeignKey("teams.id"), nullable=True, index=True)
    source: Mapped[str] = mapped_column(String(32), index=True)
    provider_player_id: Mapped[str] = mapped_column(String(64), default="")
    provider_player_name: Mapped[str] = mapped_column(String(128), default="")
    normalized_name: Mapped[str] = mapped_column(String(128), index=True)
    resolution_method: Mapped[str] = mapped_column(String(32), default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("source", "provider_player_id", name="uq_player_mapping_source"),
    )


class MatchSourceMapping(Base):
    """Source-native match ID -> canonical match. Canonical identity is
    (league, home team, away team, kickoff); provider IDs stay source-specific."""

    __tablename__ = "match_source_mappings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), index=True)
    source: Mapped[str] = mapped_column(String(32), index=True)
    source_match_id: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("source", "source_match_id", name="uq_match_mapping_source"),
    )


class RawDataRecord(Base):
    """Provenance for every imported/scraped record. The normalized DB is never
    the only copy of where data came from."""

    __tablename__ = "raw_data_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(32), index=True)
    entity_type: Mapped[str] = mapped_column(String(32), index=True)  # match|stat|event|...
    source_record_id: Mapped[str] = mapped_column(String(128), default="")
    retrieved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True)
    payload_hash: Mapped[str] = mapped_column(String(64), default="")
    parser_version: Mapped[str] = mapped_column(String(64), default="")
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    processing_status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    # pending|processed|duplicate|quarantined|failed|unresolved
    error_message: Mapped[str] = mapped_column(String(1024), default="")
    # Phase 1.7: leakage flag (verified|estimated|unknown) + origin URL/path.
    temporal_quality: Mapped[str] = mapped_column(String(16), default="unknown", index=True)
    source_url: Mapped[str] = mapped_column(String(512), default="")

    __table_args__ = (
        UniqueConstraint("source", "entity_type", "source_record_id",
                         name="uq_raw_record"),
    )


class SourceConflict(Base):
    """Sources disagree -> store all observations, never blindly overwrite."""

    __tablename__ = "source_conflicts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    match_id: Mapped[Optional[int]] = mapped_column(ForeignKey("matches.id"), nullable=True, index=True)
    entity_type: Mapped[str] = mapped_column(String(32), default="match")  # match|odds|...
    field: Mapped[str] = mapped_column(String(64), default="score")
    values: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # {source: observed}
    status: Mapped[str] = mapped_column(String(16), default="open", index=True)  # open|resolved
    resolution: Mapped[str] = mapped_column(String(512), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
