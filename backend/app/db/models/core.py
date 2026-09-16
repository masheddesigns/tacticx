"""Core football tables: leagues, teams, players, matches, stats, events, lineups, standings."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.enums import MatchStatus


class League(Base):
    __tablename__ = "leagues"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)  # EPL, UCL...
    name: Mapped[str] = mapped_column(String(128))
    country: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    provider: Mapped[str] = mapped_column(String(32), default="")
    provider_league_id: Mapped[str] = mapped_column(String(32), default="")
    season: Mapped[str] = mapped_column(String(16), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    teams: Mapped[list["Team"]] = relationship(back_populates="league")
    matches: Mapped[list["Match"]] = relationship(back_populates="league")


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    league_id: Mapped[Optional[int]] = mapped_column(ForeignKey("leagues.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(128), index=True)
    short_name: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    country: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    provider: Mapped[str] = mapped_column(String(32), default="")
    provider_team_id: Mapped[str] = mapped_column(String(32), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("provider", "provider_team_id", name="uq_team_provider"),)

    league: Mapped["Optional[League]"] = relationship(back_populates="teams")


class Player(Base):
    __tablename__ = "players"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    team_id: Mapped[Optional[int]] = mapped_column(ForeignKey("teams.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(128))
    position: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    provider: Mapped[str] = mapped_column(String(32), default="")
    provider_player_id: Mapped[str] = mapped_column(String(32), default="")

    __table_args__ = (UniqueConstraint("provider", "provider_player_id", name="uq_player_provider"),)


class Match(Base):
    __tablename__ = "matches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    league_id: Mapped[Optional[int]] = mapped_column(ForeignKey("leagues.id"), nullable=True)
    home_team_id: Mapped[Optional[int]] = mapped_column(ForeignKey("teams.id"), nullable=True)
    away_team_id: Mapped[Optional[int]] = mapped_column(ForeignKey("teams.id"), nullable=True)
    kickoff_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(16), default=MatchStatus.SCHEDULED.value, index=True)
    minute: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    home_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    away_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    provider: Mapped[str] = mapped_column(String(32), default="")
    provider_match_id: Mapped[str] = mapped_column(String(64), default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (UniqueConstraint("provider", "provider_match_id", name="uq_match_provider"),)

    league: Mapped["Optional[League]"] = relationship(back_populates="matches")


class MatchStatistic(Base):
    """One row per (match, stat_name, period). Never updated in place for finished matches;
    live rows are upserted on (match_id, stat_name, team, period)."""
    __tablename__ = "match_statistics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), index=True)
    team: Mapped[str] = mapped_column(String(8))  # home | away
    stat_name: Mapped[str] = mapped_column(String(64))  # shots, shots_on_target, possession, xg...
    stat_value: Mapped[str] = mapped_column(String(64), default="")
    period: Mapped[str] = mapped_column(String(16), default="full")  # full | 1h | 2h | live
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Phase 1.6 lineage: where/when this observation is from (point-in-time safe).
    source: Mapped[str] = mapped_column(String(32), default="")
    source_record_id: Mapped[str] = mapped_column(String(128), default="")
    effective_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("match_id", "team", "stat_name", "period", name="uq_match_stat"),
    )


class MatchEvent(Base):
    __tablename__ = "match_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), index=True)
    minute: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    event_type: Mapped[str] = mapped_column(String(32))  # goal, card, sub, var...
    detail: Mapped[str] = mapped_column(String(256), default="")
    team: Mapped[str] = mapped_column(String(8), default="")
    player_name: Mapped[str] = mapped_column(String(128), default="")
    provider: Mapped[str] = mapped_column(String(32), default="")
    provider_event_id: Mapped[str] = mapped_column(String(64), default="")
    # Phase 1.6 lineage.
    source: Mapped[str] = mapped_column(String(32), default="")
    source_record_id: Mapped[str] = mapped_column(String(128), default="")
    effective_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # Phase 1.7: stoppage time within the minute + assisting player (when provided).
    minute_added: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    assist_player: Mapped[str] = mapped_column(String(128), default="")
    # Phase 1.8: within-minute second, match period, outcome (when provided).
    second: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    period: Mapped[str] = mapped_column(String(16), default="")
    outcome: Mapped[str] = mapped_column(String(64), default="")

    __table_args__ = (UniqueConstraint("provider", "provider_event_id", name="uq_event_provider"),)


class Lineup(Base):
    __tablename__ = "lineups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), index=True)
    team_id: Mapped[Optional[int]] = mapped_column(ForeignKey("teams.id"), nullable=True)
    team: Mapped[str] = mapped_column(String(8), default="")  # home | away
    player_name: Mapped[str] = mapped_column(String(128))
    position: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    is_starting: Mapped[int] = mapped_column(Integer, default=1)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Phase 1.6 lineage.
    source: Mapped[str] = mapped_column(String(32), default="")
    source_record_id: Mapped[str] = mapped_column(String(128), default="")
    effective_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # Phase 1.7: formation + captaincy + native player id (when provided).
    formation: Mapped[str] = mapped_column(String(16), default="")
    is_captain: Mapped[int] = mapped_column(Integer, default=0)
    player_provider_id: Mapped[str] = mapped_column(String(64), default="")
    # Phase 1.8: squad number (when provided).
    jersey_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    __table_args__ = (
        UniqueConstraint("match_id", "team", "player_name", name="uq_lineup_player"),
    )


class TeamStatistic(Base):
    __tablename__ = "team_statistics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)
    league_id: Mapped[Optional[int]] = mapped_column(ForeignKey("leagues.id"), nullable=True)
    season: Mapped[str] = mapped_column(String(16), default="")
    stat_name: Mapped[str] = mapped_column(String(64))
    stat_value: Mapped[str] = mapped_column(String(64), default="")
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Phase 1.6 lineage.
    source: Mapped[str] = mapped_column(String(32), default="")
    source_record_id: Mapped[str] = mapped_column(String(128), default="")
    effective_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("team_id", "league_id", "season", "stat_name", name="uq_team_stat"),
    )


class Standing(Base):
    __tablename__ = "standings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    league_id: Mapped[int] = mapped_column(ForeignKey("leagues.id"), index=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)
    season: Mapped[str] = mapped_column(String(16), default="")
    position: Mapped[int] = mapped_column(Integer, default=0)
    played: Mapped[int] = mapped_column(Integer, default=0)
    won: Mapped[int] = mapped_column(Integer, default=0)
    drawn: Mapped[int] = mapped_column(Integer, default=0)
    lost: Mapped[int] = mapped_column(Integer, default=0)
    points: Mapped[int] = mapped_column(Integer, default=0)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Phase 1.6 lineage: backtests must see pre-kickoff standings via effective_at.
    source: Mapped[str] = mapped_column(String(32), default="")
    source_record_id: Mapped[str] = mapped_column(String(128), default="")
    effective_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (UniqueConstraint("league_id", "team_id", "season", name="uq_standing"),)
