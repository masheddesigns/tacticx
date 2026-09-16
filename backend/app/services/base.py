"""Abstract provider interfaces — swap implementations without touching the app."""
from __future__ import annotations

from typing import Optional

from abc import ABC, abstractmethod
from app.services.dtos import (
    EventDTO, FixtureDTO, LeagueDTO, LineupEntryDTO, OddsSnapshotDTO,
    StandingDTO, StatDTO, TeamDTO,
)


class FootballDataProvider(ABC):
    provider_name: str = "base"

    @abstractmethod
    async def get_leagues(self) -> list[LeagueDTO]: ...

    @abstractmethod
    async def get_teams(self, league_id: str, season: str) -> list[TeamDTO]: ...

    @abstractmethod
    async def get_fixtures(self, league_id: str, season: str, date: Optional[str] = None) -> list[FixtureDTO]: ...

    @abstractmethod
    async def get_match(self, match_id: str) -> Optional[FixtureDTO]: ...

    @abstractmethod
    async def get_match_statistics(self, match_id: str) -> list[StatDTO]: ...

    @abstractmethod
    async def get_match_events(self, match_id: str) -> list[EventDTO]: ...

    @abstractmethod
    async def get_lineups(self, match_id: str) -> list[LineupEntryDTO]: ...

    @abstractmethod
    async def get_team_statistics(self, league_id: str, season: str, team_id: str) -> list[StatDTO]: ...

    @abstractmethod
    async def get_standings(self, league_id: str, season: str) -> list[StandingDTO]: ...


class OddsProvider(ABC):
    provider_name: str = "base"

    @abstractmethod
    async def get_odds(self, match_hint: Optional[str] = None) -> list[OddsSnapshotDTO]: ...

    @abstractmethod
    async def get_live_odds(self, match_hint: Optional[str] = None) -> list[OddsSnapshotDTO]: ...

    @abstractmethod
    async def get_markets(self) -> list[str]: ...

    @abstractmethod
    async def get_bookmakers(self) -> list[str]: ...
