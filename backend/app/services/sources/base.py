"""Generic source interfaces (Phase 1.6).

Three axes — football entities, odds, bulk history — so prediction code can
depend on normalized records while adapters come and go. Existing
FootballDataProvider/OddsProvider implementations are wrapped, not rewritten
(see sources/football/api_football_source.py, sources/odds/odds_api_source.py).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from pydantic import BaseModel

from app.services.sources.normalized import (
    NormalizedEvent,
    NormalizedLineup,
    NormalizedMatch,
    NormalizedMatchStatistics,
    NormalizedOddsSnapshot,
    NormalizedPlayer,
    NormalizedStanding,
    NormalizedTeam,
)


class SourceCapabilities(BaseModel):
    leagues: bool = False
    teams: bool = False
    fixtures: bool = False
    match_detail: bool = False       # statistics / events / lineups
    standings: bool = False
    odds_prematch: bool = False
    odds_live: bool = False
    historical_bulk: bool = False


class DataSource(ABC):
    """Common ground: every source has a name, capabilities, and a health check."""

    source_name: str = "base"
    capabilities: SourceCapabilities = SourceCapabilities()

    @abstractmethod
    def check(self) -> dict:
        """Lightweight availability probe. Must never raise on failure."""
        ...


class FootballDataSource(DataSource, ABC):
    @abstractmethod
    async def get_leagues(self) -> list[dict]:
        """Return [{'code','name','country','provider_league_id','season'}]."""
        ...

    @abstractmethod
    async def get_teams(self, league_code: str, season: str) -> list[NormalizedTeam]:
        ...

    @abstractmethod
    async def get_fixtures(
        self,
        league_code: str,
        season: str,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> list[NormalizedMatch]:
        ...

    @abstractmethod
    async def get_match_statistics(self, source_match_id: str) -> list[NormalizedMatchStatistics]:
        ...

    @abstractmethod
    async def get_match_events(self, source_match_id: str) -> list[NormalizedEvent]:
        ...

    @abstractmethod
    async def get_lineups(self, source_match_id: str) -> list[NormalizedLineup]:
        ...

    @abstractmethod
    async def get_standings(self, league_code: str, season: str) -> list[NormalizedStanding]:
        ...

    @abstractmethod
    async def get_players(self, league_code: str, season: str) -> list[NormalizedPlayer]:
        ...


class OddsDataSource(DataSource, ABC):
    @abstractmethod
    async def get_odds_snapshots(
        self,
        league_code: str = "",
        season: str = "",
        live: bool = False,
    ) -> list[NormalizedOddsSnapshot]:
        """Append-only observations; one entry per bookmaker+market."""
        ...

    @abstractmethod
    def supported_markets(self) -> list[str]:
        """Markets this source ACTUALLY provides. Never invented."""
        ...


class HistoricalDataSource(DataSource, ABC):
    @abstractmethod
    def import_history(
        self,
        league_code: str,
        season: str,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        **kwargs,
    ) -> dict:
        """Bulk import of finished matches (+ stats/odds where available).

        Synchronous (file/parse bound). Returns an import report dict with
        keys: records_read, valid, inserted, updated, duplicates_skipped,
        invalid, errors.
        """
        ...
