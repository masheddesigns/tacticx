"""API-Football as a source-agnostic FootballDataSource (Phase 1.6).

Thin wrapper around the existing ApiFootballProvider — parsing stays in the
provider; this layer only converts provider DTOs to Normalized* records.
APIs are fallback/validation sources, not the bulk foundation.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from app.config import get_settings
from app.services.football.api_football import ApiFootballProvider
from app.services.sources.base import FootballDataSource, SourceCapabilities
from app.services.sources.normalized import (
    NormalizedEvent,
    NormalizedLineup,
    NormalizedMatch,
    NormalizedMatchStatistics,
    NormalizedPlayer,
    NormalizedStanding,
    NormalizedTeam,
    Provenance,
)

MAX_RANGE_DAYS = 31


def _prov(source: str, record_id: str, parser: str, live: bool = False) -> Provenance:
    from app.services.scraping.framework import utcnow

    now = utcnow()
    return Provenance(source=source, source_record_id=str(record_id),
                      collected_at=now,
                      # Live API data: observed now, effective now -> verified.
                      # Historical pulls: timing inferred -> estimated.
                      effective_at=now if live else None,
                      temporal_quality="verified" if live else "estimated",
                      parser_version=parser)


class ApiFootballSource(FootballDataSource):
    source_name = "api_football"
    capabilities = SourceCapabilities(leagues=True, teams=True, fixtures=True,
                                      match_detail=True, standings=True)

    PARSER = "api_football_parser_v1"

    def __init__(self, api_key: str = "", base_url: str = "", db_session_factory=None,
                 client=None, **kwargs):
        self.provider = ApiFootballProvider(api_key=api_key, base_url=base_url,
                                            db_session_factory=db_session_factory, client=client)

    def check(self) -> dict:
        s = get_settings()
        return {"source": self.source_name,
                "configured": bool(s.FOOTBALL_API_KEY.strip()),
                "role": "fallback/validation (free-plan limits apply)"}

    def _league_entry(self, league_code: str) -> dict:
        for entry in get_settings().supported_leagues_parsed():
            if entry["code"] == league_code:
                return entry
        raise ValueError(f"league {league_code!r} not configured (SUPPORTED_LEAGUES)")

    async def get_leagues(self) -> list[dict]:
        return [
            {"code": dto.code, "name": dto.name, "country": dto.country,
             "provider_league_id": dto.provider_league_id, "season": dto.season}
            for dto in await self.provider.get_leagues()
        ]

    async def get_teams(self, league_code: str, season: str) -> list[NormalizedTeam]:
        entry = self._league_entry(league_code)
        out = []
        for dto in await self.provider.get_teams(entry["provider_id"], season or entry["season"]):
            out.append(NormalizedTeam(
                name=dto.name, short_name=dto.short_name, country=dto.country,
                league_code=league_code, provider_team_id=dto.provider_team_id,
                provenance=_prov(self.source_name, dto.provider_team_id, self.PARSER)))
        return out

    async def get_fixtures(self, league_code: str, season: str,
                           date_from: Optional[str] = None,
                           date_to: Optional[str] = None) -> list[NormalizedMatch]:
        entry = self._league_entry(league_code)
        season = season or entry["season"]
        days = self._iter_days(date_from, date_to)
        out = []
        for day in days:
            data = await self.provider._get(
                "/fixtures",
                {"league": entry["provider_id"], "season": season, "from": day, "to": day},
                ttl=300)
            rows = data.get("response", []) if isinstance(data, dict) else []
            for row in rows:
                if isinstance(row, dict):
                    out.append(self._convert_fixture(row, league_code, season))
        return out

    @staticmethod
    def _iter_days(date_from: Optional[str], date_to: Optional[str]) -> list[str]:
        if not date_from and not date_to:
            raise ValueError("api_football source requires date_from/date_to (quota-safe bounded fetch)")
        start = date.fromisoformat(date_from or date_to or "")
        end = date.fromisoformat(date_to or date_from or "")
        if end < start:
            raise ValueError("date_to before date_from")
        if (end - start).days > MAX_RANGE_DAYS:
            raise ValueError(f"range exceeds {MAX_RANGE_DAYS} days — chunk the collection")
        return [(start + timedelta(days=i)).isoformat() for i in range((end - start).days + 1)]

    def _convert_fixture(self, row: dict, league_code: str, season: str) -> NormalizedMatch:
        dto = self.provider._parse_fixture(row)
        return NormalizedMatch(
            league_code=league_code, season=season,
            home_team=dto.home_team_name, home_team_id=dto.home_team_id,
            away_team=dto.away_team_name, away_team_id=dto.away_team_id,
            kickoff_at=dto.kickoff_at, status=dto.status, minute=dto.minute,
            home_score=dto.home_score, away_score=dto.away_score,
            provider_match_id=dto.provider_match_id,
            provenance=_prov(self.source_name, dto.provider_match_id, self.PARSER))

    async def get_match_statistics(self, source_match_id: str) -> list[NormalizedMatchStatistics]:
        return [
            NormalizedMatchStatistics(
                team=s.team, stat_name=s.stat_name, stat_value=s.stat_value, period=s.period,
                provenance=_prov(self.source_name, f"{source_match_id}:{s.team}:{s.stat_name}",
                                 self.PARSER))
            for s in await self.provider.get_match_statistics(source_match_id)
        ]

    async def get_match_events(self, source_match_id: str) -> list[NormalizedEvent]:
        return [
            NormalizedEvent(
                minute=e.minute, minute_added=e.minute_added, event_type=e.event_type,
                detail=e.detail, team=e.team, player_name=e.player_name,
                assist_player=e.assist_player, provider_player_id=e.provider_player_id,
                provenance=_prov(self.source_name, e.provider_event_id, self.PARSER))
            for e in await self.provider.get_match_events(source_match_id)
        ]

    async def get_lineups(self, source_match_id: str) -> list[NormalizedLineup]:
        return [
            NormalizedLineup(
                team=lu.team, player_name=lu.player_name, position=lu.position,
                is_starting=lu.is_starting, formation=lu.formation,
                is_captain=lu.is_captain, provider_player_id=lu.provider_player_id,
                provenance=_prov(self.source_name, f"{source_match_id}:{lu.team}:{lu.player_name}",
                                 self.PARSER))
            for lu in await self.provider.get_lineups(source_match_id)
        ]

    async def get_standings(self, league_code: str, season: str) -> list[NormalizedStanding]:
        entry = self._league_entry(league_code)
        return [
            NormalizedStanding(
                team_name=s.team_name, team_provider_id=s.team_provider_id,
                position=s.position, played=s.played, won=s.won, drawn=s.drawn,
                lost=s.lost, points=s.points,
                provenance=_prov(self.source_name, s.team_provider_id, self.PARSER))
            for s in await self.provider.get_standings(entry["provider_id"], season or entry["season"])
        ]

    async def get_players(self, league_code: str, season: str) -> list[NormalizedPlayer]:
        return []  # not offered by this source; absent, never invented
