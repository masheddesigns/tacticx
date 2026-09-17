"""Phase 9 player-intelligence tables (additive only).

No historical record is mutated: snapshots are versioned rows, memberships
are validity-ranged rows, provenance references canonical IDs. Identity
infrastructure from Phase 8 is reused, never duplicated.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PlayerFeatureSnapshot(Base):
    """Versioned player-feature payload for one (match, cutoff, mode)."""

    __tablename__ = "player_feature_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), index=True)
    cutoff: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    feature_version: Mapped[str] = mapped_column(String(32), default="player_features_v1")
    mode: Mapped[str] = mapped_column(String(32), default="strict_prematch")
    payload: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    payload_hash: Mapped[str] = mapped_column(String(64), default="", index=True)
    provenance: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_player_snap_match_cutoff", "match_id", "cutoff"),
    )


class PlayerTeamMembership(Base):
    """Versioned player-team membership reconstructed from lineup rows."""

    __tablename__ = "player_team_memberships"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), index=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)
    valid_from: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True)
    valid_to: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True)
    source: Mapped[str] = mapped_column(String(32), default="")
    confidence: Mapped[str] = mapped_column(String(16), default="unknown")

    __table_args__ = (
        Index("ix_membership_player_team", "player_id", "team_id"),
    )


class PlayerFeatureProvenance(Base):
    """Per-feature provenance for player features (feature, source, IDs)."""

    __tablename__ = "player_feature_provenance"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(
        ForeignKey("player_feature_snapshots.id"), index=True)
    feature_name: Mapped[str] = mapped_column(String(128), index=True)
    source: Mapped[str] = mapped_column(String(32), default="")
    source_record_ids: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    canonical_ids: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    quality: Mapped[str] = mapped_column(String(16), default="unknown")
