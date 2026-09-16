"""API-Football (api-sports) adapter — first football provider.

Docs: https://www.api-football.com/documentation-v3
Key goes in FOOTBALL_API_KEY. All parsing is defensive: missing fields -> defaults,
never fake data.
"""
from __future__ import annotations

from typing import Optional

from datetime import datetime, timezone

from app.config import get_settings
from app.services.base import FootballDataProvider
from app.services.dtos import (
    EventDTO, FixtureDTO, LeagueDTO, LineupEntryDTO, StandingDTO, StatDTO, TeamDTO,
)
from app.services.http_client import logged_request

STATUS_MAP = {
    "NS": "SCHEDULED", "TBD": "SCHEDULED", "PST": "POSTPONED", "CANC": "CANCELLED",
    "ABD": "CANCELLED", "AWD": "FINISHED", "WO": "FINISHED",
    "FT": "FINISHED", "AET": "FINISHED", "PEN": "FINISHED",
    "1H": "LIVE", "2H": "LIVE", "ET": "LIVE", "P": "LIVE", "LIVE": "LIVE",
    "HT": "HALFTIME", "BT": "HALFTIME",
}


class ApiFootballProvider(FootballDataProvider):
    provider_name = "api_football"

    def __init__(self, api_key: str = "", base_url: str = "", db_session_factory=None,
                 client=None):
        s = get_settings()
        self.api_key = api_key or s.FOOTBALL_API_KEY
        self.base_url = (base_url or s.FOOTBALL_API_BASE_URL).rstrip("/")
        self.db_session_factory = db_session_factory
        self.client = client

    def _headers(self) -> dict:
        return {"x-apisports-key": self.api_key}

    async def _get(self, path: str, params: Optional[dict] = None, ttl: int = 900) -> dict:
        key = f"fb:{path}:{sorted((params or {}).items())}"
        return await logged_request(
            self.provider_name, "GET", f"{self.base_url}{path}",
            headers=self._headers(), params=params,
            cache_key=key, cache_ttl=ttl,
            db_session_factory=self.db_session_factory, client=self.client,
        ) or {}

    async def get_leagues(self) -> list[LeagueDTO]:
        out = []
        for entry in get_settings().supported_leagues_parsed():
            out.append(LeagueDTO(
                code=entry["code"], name=entry["code"].replace("_", " ").title(),
                provider=self.provider_name, provider_league_id=entry["provider_id"],
                season=entry["season"],
            ))
        return out

    @staticmethod
    def _rows(data: dict, key: str = "response") -> list:
        rows = data.get(key, []) if isinstance(data, dict) else []
        return [r for r in rows if isinstance(r, dict)]

    async def get_teams(self, league_id: str, season: str) -> list[TeamDTO]:
        data = await self._get("/teams", {"league": league_id, "season": season}, ttl=86400)
        teams = []
        for row in self._rows(data):
            t = row.get("team", {})
            if not isinstance(t, dict):
                continue
            teams.append(TeamDTO(
                name=t.get("name", ""), short_name=t.get("code"),
                country=t.get("country"), provider=self.provider_name,
                provider_team_id=str(t.get("id", "")),
            ))
        return teams

    async def get_fixtures(self, league_id: str, season: str, date: Optional[str] = None) -> list[FixtureDTO]:
        params: dict = {"league": league_id, "season": season}
        if date:
            params["date"] = date
        data = await self._get("/fixtures", params, ttl=3600)
        return [self._parse_fixture(r) for r in self._rows(data)]

    async def get_match(self, match_id: str) -> Optional[FixtureDTO]:
        data = await self._get("/fixtures", {"id": match_id}, ttl=300)
        rows = self._rows(data)
        return self._parse_fixture(rows[0]) if rows else None

    async def get_match_statistics(self, match_id: str) -> list[StatDTO]:
        data = await self._get("/fixtures/statistics", {"fixture": match_id}, ttl=120)
        out: list[StatDTO] = []
        # Provider returns one entry per team, home first (observed, not
        # contractual — team identity per row is not supplied by this endpoint).
        team_side = "home"
        for row in self._rows(data):
            if not isinstance(row.get("statistics", []), list):
                continue
            for stat in row.get("statistics", []):
                if not isinstance(stat, dict):
                    continue
                out.append(StatDTO(
                    team=team_side, stat_name=str(stat.get("type", "")).lower().replace(" ", "_"),
                    stat_value=str(stat.get("value", "")), period="full",
                ))
            team_side = "away"
        return out

    async def get_match_events(self, match_id: str) -> list[EventDTO]:
        data = await self._get("/fixtures/events", {"fixture": match_id}, ttl=120)
        out = []
        for i, e in enumerate(self._rows(data)):
            time_info = e.get("time", {}) if isinstance(e.get("time", {}), dict) else {}
            team_info = e.get("team", {}) if isinstance(e.get("team", {}), dict) else {}
            player_info = e.get("player", {}) if isinstance(e.get("player", {}), dict) else {}
            assist_info = e.get("assist", {}) if isinstance(e.get("assist", {}), dict) else {}
            try:
                extra = time_info.get("extra")
                minute_added = int(extra) if extra is not None else None
            except (TypeError, ValueError):
                minute_added = None
            out.append(EventDTO(
                provider=self.provider_name,
                provider_event_id=f"{match_id}-{i}-{time_info.get('elapsed', 0)}"
                                  f"-{e.get('type', '')}-{e.get('detail', '')}",
                minute=time_info.get("elapsed"),
                minute_added=minute_added,
                event_type=str(e.get("type", "")).lower(),
                detail=str(e.get("detail", "")),
                team=str(team_info.get("name", "")),
                player_name=str(player_info.get("name", "")),
                assist_player=str(assist_info.get("name", "") or ""),
                provider_player_id=str(player_info.get("id", "") or ""),
            ))
        return out

    async def get_lineups(self, match_id: str) -> list[LineupEntryDTO]:
        data = await self._get("/fixtures/lineups", {"fixture": match_id}, ttl=600)
        out = []
        for idx, row in enumerate(self._rows(data)):
            side = "home" if idx == 0 else "away"
            formation = str(row.get("formation", "") or "")
            for group, starting in (("startXI", 1), ("substitutes", 0)):
                members = row.get(group, [])
                if not isinstance(members, list):
                    continue
                for p in members:
                    if not isinstance(p, dict):
                        continue
                    pl = p.get("player", {})
                    if not isinstance(pl, dict):
                        continue
                    out.append(LineupEntryDTO(team=side, player_name=pl.get("name", ""),
                                              position=pl.get("pos"), is_starting=starting,
                                              formation=formation,
                                              provider_player_id=str(pl.get("id", "") or "")))
        return out

    async def get_team_statistics(self, league_id: str, season: str, team_id: str) -> list[StatDTO]:
        data = await self._get("/teams/statistics",
                               {"league": league_id, "season": season, "team": team_id}, ttl=86400)
        return [StatDTO(team="home", stat_name="raw", stat_value=str(data.get("response", ""))[:200])]

    async def get_standings(self, league_id: str, season: str) -> list[StandingDTO]:
        data = await self._get("/standings", {"league": league_id, "season": season}, ttl=21600)
        out = []
        tables = data.get("response", []) if isinstance(data, dict) else []
        for table in tables:
            if not isinstance(table, dict):
                continue
            league_info = table.get("league", {})
            groups = league_info.get("standings", []) if isinstance(league_info, dict) else []
            for group in groups if isinstance(groups, list) else []:
                for row in group if isinstance(group, list) else []:
                    if not isinstance(row, dict):
                        continue
                    team_info = row.get("team", {}) if isinstance(row.get("team", {}), dict) else {}
                    all_info = row.get("all", {}) if isinstance(row.get("all", {}), dict) else {}
                    out.append(StandingDTO(
                        team_provider_id=str(team_info.get("id", "")),
                        team_name=team_info.get("name", ""),
                        position=row.get("rank", 0) or 0,
                        played=all_info.get("played", 0) or 0,
                        won=all_info.get("win", 0) or 0,
                        drawn=all_info.get("draw", 0) or 0,
                        lost=all_info.get("lose", 0) or 0,
                        points=row.get("points", 0) or 0,
                    ))
        return out

    def _parse_fixture(self, row: dict) -> FixtureDTO:
        fx = row.get("fixture", {})
        lg = row.get("league", {})
        teams = row.get("teams", {})
        goals = row.get("goals", {})
        score = row.get("score", {})
        short = fx.get("status", {}).get("short", "NS")
        kickoff = fx.get("date")
        try:
            kickoff_dt = datetime.fromisoformat(kickoff) if kickoff else None
            if kickoff_dt is not None and kickoff_dt.tzinfo is None:
                kickoff_dt = kickoff_dt.replace(tzinfo=timezone.utc)
        except ValueError:
            kickoff_dt = None
        home = teams.get("home", {})
        away = teams.get("away", {})
        return FixtureDTO(
            provider=self.provider_name,
            provider_match_id=str(fx.get("id", "")),
            league_code=str(lg.get("id", "")),
            home_team_id=str(home.get("id", "")), home_team_name=home.get("name", ""),
            away_team_id=str(away.get("id", "")), away_team_name=away.get("name", ""),
            kickoff_at=kickoff_dt,
            status=STATUS_MAP.get(short, "SCHEDULED"),
            minute=fx.get("status", {}).get("elapsed"),
            home_score=goals.get("home"), away_score=goals.get("away"),
        )
