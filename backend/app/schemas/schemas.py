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
    # Phase 2 audit fields (optional so older responses still validate).
    model_name: Optional[str] = None
    status: Optional[str] = None
    temporal_mode: Optional[str] = None
    prediction_cutoff: Optional[datetime] = None
    feature_availability: Optional[dict] = None
    model_configuration: Optional[dict] = None
    random_seed: Optional[int] = None


class FullPredictionOut(BaseModel):
    """Complete Phase 2 prediction payload (probabilities, never certainties)."""
    model_name: str = ""
    model_version: str = ""
    status: str = "valid"
    home_win_probability: float = 0.0
    draw_probability: float = 0.0
    away_win_probability: float = 0.0
    expected_home_goals: Optional[float] = None
    expected_away_goals: Optional[float] = None
    expected_total_goals: Optional[float] = None
    over_1_5_probability: Optional[float] = None
    under_1_5_probability: Optional[float] = None
    over_2_5_probability: Optional[float] = None
    under_2_5_probability: Optional[float] = None
    over_3_5_probability: Optional[float] = None
    under_3_5_probability: Optional[float] = None
    btts_yes_probability: Optional[float] = None
    btts_no_probability: Optional[float] = None
    score_probabilities: Optional[dict] = None
    confidence: Optional[float] = None
    xg_used: bool = False
    feature_availability: Optional[dict] = None
    temporal_mode: str = "strict_prematch"
    prediction_cutoff: Optional[str] = None
    random_seed: Optional[int] = None
    data_quality: Optional[list] = None
    prediction_id: Optional[int] = None


class BacktestRunOut(BaseModel):
    id: int
    model_name: str = ""
    model_version: str = ""
    league: str = ""
    season: str = ""
    temporal_mode: str = "strict_prematch"
    sample_size: int = 0
    excluded_insufficient: int = 0
    excluded_temporal: int = 0
    metrics: Optional[dict] = None
    created_at: Optional[datetime] = None
