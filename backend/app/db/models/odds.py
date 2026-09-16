"""Odds tables. Odds are append-only historical snapshots — never overwritten."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Bookmaker(Base):
    __tablename__ = "bookmakers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    provider: Mapped[str] = mapped_column(String(32), default="")
    provider_bookmaker_id: Mapped[str] = mapped_column(String(64), default="")

    __table_args__ = (UniqueConstraint("provider", "provider_bookmaker_id", name="uq_bookmaker"),)


class Market(Base):
    __tablename__ = "markets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    market_key: Mapped[str] = mapped_column(String(64), unique=True)  # h2h, totals, btts
    description: Mapped[str] = mapped_column(String(256), default="")


class OddsSnapshot(Base):
    """One polling event per (match, bookmaker, market, timestamp)."""
    __tablename__ = "odds_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), index=True)
    bookmaker_id: Mapped[Optional[int]] = mapped_column(ForeignKey("bookmakers.id"), nullable=True)
    market_type: Mapped[str] = mapped_column(String(64), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    source: Mapped[str] = mapped_column(String(32), default="")
    is_live: Mapped[bool] = mapped_column(Boolean, default=False)
    # Phase 1.6 lineage: source-native event/market IDs for traceability.
    source_event_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    source_market_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)


class OddsSelection(Base):
    """One outcome row per snapshot. Dedup key prevents accidental duplicates."""
    __tablename__ = "odds_selections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("odds_snapshots.id"), index=True)
    selection: Mapped[str] = mapped_column(String(64))  # home | draw | away | over_2_5 ...
    odds: Mapped[float] = mapped_column(Float)
    point: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # totals line, e.g. 2.5
    dedup_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
