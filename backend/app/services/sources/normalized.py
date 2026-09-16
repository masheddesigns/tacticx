"""Source-agnostic normalized records (Phase 1.6).

Every adapter emits THESE — never provider-specific DB models. Provenance
travels with each record so backtests can reconstruct point-in-time state:
event/match date, source, source record ID, collected/published/effective
timestamps, and the parser version that produced it.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class Provenance(BaseModel):
    source: str = ""                    # adapter name, e.g. "csv", "football_data_co_uk"
    source_record_id: str = ""          # provider-native ID (match id, CSV row key...)
    collected_at: Optional[datetime] = None   # when WE fetched/imported it
    published_at: Optional[datetime] = None   # when the source published it (if known)
    effective_at: Optional[datetime] = None   # when it became true (defaults to event time)
    parser_version: str = ""            # e.g. "csv_match_parser_v1"
    # Leakage flag for Phase 2 filtering: verified | estimated | unknown.
    # verified = timing chain fully known; estimated = event time known but
    #   publication/collection inferred; unknown = cannot be established.
    # Never deleted, only flagged.
    temporal_quality: str = "unknown"
    source_url: str = ""                # download URL or file path (provenance)


class NormalizedTeam(BaseModel):
    name: str
    short_name: Optional[str] = None
    country: Optional[str] = None
    league_code: Optional[str] = None
    provider_team_id: str = ""          # native ID within source ("" when N/A, e.g. CSV)
    provenance: Provenance = Field(default_factory=Provenance)


class NormalizedPlayer(BaseModel):
    name: str
    team_name: str = ""
    team_provider_id: str = ""
    position: Optional[str] = None
    provider_player_id: str = ""
    provenance: Provenance = Field(default_factory=Provenance)


class NormalizedMatch(BaseModel):
    league_code: str = ""
    season: str = ""
    home_team: str = ""
    home_team_id: str = ""              # native ID within source ("" when N/A)
    away_team: str = ""
    away_team_id: str = ""
    kickoff_at: Optional[datetime] = None
    status: str = "SCHEDULED"
    minute: Optional[int] = None
    home_score: Optional[int] = None
    away_score: Optional[int] = None
    provider_match_id: str = ""         # native match ID within source
    provenance: Provenance = Field(default_factory=Provenance)


class NormalizedMatchStatistics(BaseModel):
    team: str = ""                      # home | away | team name (resolved later)
    stat_name: str = ""
    stat_value: str = ""
    period: str = "full"
    provenance: Provenance = Field(default_factory=Provenance)


class NormalizedEvent(BaseModel):
    minute: Optional[int] = None
    minute_added: Optional[int] = None  # stoppage time within the minute (45+2 -> 2)
    second: Optional[int] = None        # within-minute second (when provided)
    period: str = ""                    # e.g. "1H" | "2H" (when provided)
    event_type: str = ""                # goal|own_goal|penalty|missed_penalty|
                                        # yellow_card|red_card|second_yellow|substitution|var
    detail: str = ""
    team: str = ""
    player_name: str = ""
    assist_player: str = ""             # when the source provides it, else ""
    provider_player_id: str = ""
    outcome: str = ""                   # e.g. shot outcome (when provided)
    provenance: Provenance = Field(default_factory=Provenance)


class NormalizedLineup(BaseModel):
    team: str = ""
    player_name: str = ""
    position: Optional[str] = None
    is_starting: int = 1
    formation: str = ""                 # e.g. "4-3-3", when provided
    is_captain: int = 0                 # 1 only when the source flags captaincy
    jersey_number: Optional[int] = None
    provider_player_id: str = ""
    provenance: Provenance = Field(default_factory=Provenance)


class NormalizedStanding(BaseModel):
    team_name: str = ""
    team_provider_id: str = ""
    position: int = 0
    played: int = 0
    won: int = 0
    drawn: int = 0
    lost: int = 0
    points: int = 0
    provenance: Provenance = Field(default_factory=Provenance)


class NormalizedOddsSelection(BaseModel):
    selection: str = ""                 # home | draw | away | over_2.5 | ...
    price: float = 0.0                  # decimal; validated > 1.0 by quality layer
    point: Optional[float] = None       # totals/handicap line
    bookmaker: str = ""
    bookmaker_id: str = ""


class NormalizedOddsSnapshot(BaseModel):
    """One bookmaker+market observation. Never overwritten downstream."""
    league_code: str = ""
    season: str = ""
    home_team: str = ""
    away_team: str = ""
    kickoff_at: Optional[datetime] = None
    market: str = ""                    # h2h | totals | ... only when source provides it
    timestamp: Optional[datetime] = None
    collected_at: Optional[datetime] = None
    is_live: bool = False
    source: str = ""
    source_event_id: str = ""
    source_market_id: str = ""
    selections: list[NormalizedOddsSelection] = Field(default_factory=list)
    provenance: Provenance = Field(default_factory=Provenance)
