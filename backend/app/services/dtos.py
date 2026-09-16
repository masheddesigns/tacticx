"""Normalized DTOs shared by all provider adapters (football + odds)."""
from __future__ import annotations

from typing import Optional

from datetime import datetime
from pydantic import BaseModel, Field


class LeagueDTO(BaseModel):
    code: str = ""
    name: str
    country: Optional[str] = None
    provider: str = ""
    provider_league_id: str = ""
    season: str = ""


class TeamDTO(BaseModel):
    name: str
    short_name: Optional[str] = None
    country: Optional[str] = None
    provider: str = ""
    provider_team_id: str = ""
    league_code: Optional[str] = None


class FixtureDTO(BaseModel):
    provider: str = ""
    provider_match_id: str
    league_code: Optional[str] = None
    home_team_id: str = ""
    home_team_name: str = ""
    away_team_id: str = ""
    away_team_name: str = ""
    kickoff_at: Optional[datetime] = None
    status: str = "SCHEDULED"
    minute: Optional[int] = None
    home_score: Optional[int] = None
    away_score: Optional[int] = None


class StatDTO(BaseModel):
    team: str  # home | away
    stat_name: str
    stat_value: str
    period: str = "full"


class EventDTO(BaseModel):
    provider: str = ""
    provider_event_id: str
    minute: Optional[int] = None
    minute_added: Optional[int] = None  # stoppage time within the minute
    event_type: str = ""
    detail: str = ""
    team: str = ""
    player_name: str = ""
    assist_player: str = ""
    provider_player_id: str = ""


class LineupEntryDTO(BaseModel):
    team: str
    player_name: str
    position: Optional[str] = None
    is_starting: int = 1
    formation: str = ""
    is_captain: int = 0
    provider_player_id: str = ""


class StandingDTO(BaseModel):
    team_provider_id: str
    team_name: str = ""
    position: int = 0
    played: int = 0
    won: int = 0
    drawn: int = 0
    lost: int = 0
    points: int = 0


class OddsSelectionDTO(BaseModel):
    selection: str
    odds: float = Field(gt=1.0)
    point: Optional[float] = None


class OddsSnapshotDTO(BaseModel):
    """One bookmaker+market poll. Selections hang off it."""
    bookmaker: str = ""
    bookmaker_provider_id: str = ""
    market_type: str = ""
    timestamp: Optional[datetime] = None
    is_live: bool = False
    selections: list[OddsSelectionDTO] = Field(default_factory=list)
    # Event context (when the provider supplies it) so odds can be
    # matched to our matches. Absent -> leave unset, never guess.
    event_id: Optional[str] = None
    home_team: Optional[str] = None
    away_team: Optional[str] = None
    commence_time: Optional[datetime] = None
