"""Pydantic response schemas (dashboard contract)."""
from __future__ import annotations

from typing import Optional

from datetime import datetime
from pydantic import BaseModel


class PaginatedMeta(BaseModel):
    page: int
    page_size: int
    total: int


class LeagueOut(BaseModel):
    id: int
    code: str
    name: str
    country: Optional[str] = None
    season: str = ""


class TeamOut(BaseModel):
    id: int
    name: str
    short_name: Optional[str] = None
    country: Optional[str] = None


class MatchOut(BaseModel):
    id: int
    league_id: Optional[int] = None
    home_team_id: Optional[int] = None
    away_team_id: Optional[int] = None
    home_team_name: Optional[str] = None
    away_team_name: Optional[str] = None
    kickoff_at: Optional[datetime] = None
    status: str
    minute: Optional[int] = None
    home_score: Optional[int] = None
    away_score: Optional[int] = None


class StatOut(BaseModel):
    team: str
    stat_name: str
    stat_value: str
    period: str


class EventOut(BaseModel):
    minute: Optional[int] = None
    event_type: str
    detail: str = ""
    team: str = ""
    player_name: str = ""


class OddsSelectionOut(BaseModel):
    selection: str
    odds: float
    point: Optional[float] = None
    timestamp: Optional[datetime] = None


class OddsSnapshotOut(BaseModel):
    bookmaker: str
    market_type: str
    timestamp: Optional[datetime] = None
    is_live: bool
    selections: list[OddsSelectionOut] = []


class OddsMovementOut(BaseModel):
    bookmaker: str
    market_type: str
    selection: str
    opening: float
    current: float
    absolute_change: float
    percentage_change: float
    direction: str
    velocity_per_hour: Optional[float] = None


class PredictionOut(BaseModel):
    id: int
    match_id: int
    prediction_timestamp: Optional[datetime] = None
    model_version: str
    prediction_type: str
    predicted_probability: float
    probabilities: Optional[dict] = None
    confidence: Optional[float] = None
