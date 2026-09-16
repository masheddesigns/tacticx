"""The-Odds-API adapter — first odds provider.

Docs: https://the-odds-api.com/liveapi/guides/v4/
Key goes in ODDS_API_KEY. Regions/markets from ODDS_REGIONS / ODDS_MARKETS.
"""
from __future__ import annotations

from typing import Optional

from datetime import datetime, timezone

from app.config import get_settings
from app.services.base import OddsProvider
from app.services.dtos import OddsSelectionDTO, OddsSnapshotDTO
from app.services.http_client import logged_request

OUTCOME_MAP = {"Home": "home", "Draw": "draw", "Away": "away", "Over": "over", "Under": "under",
               "Yes": "yes", "No": "no"}

# Our league codes -> The Odds API sport keys. Unknown leagues fall back to EPL.
LEAGUE_SPORT_KEYS = {
    "EPL": "soccer_epl",
    "LA_LIGA": "soccer_spain_la_liga",
    "SERIE_A": "soccer_italy_serie_a",
    "BUNDESLIGA": "soccer_germany_bundesliga",
    "LIGUE_1": "soccer_france_ligue_one",
    "UCL": "soccer_uefa_champs_league",
}

DEFAULT_SPORT_KEY = "soccer_epl"


class OddsApiProvider(OddsProvider):
    provider_name = "odds_api"

    def __init__(self, api_key: str = "", base_url: str = "", db_session_factory=None, client=None):
        s = get_settings()
        self.api_key = api_key or s.ODDS_API_KEY
        self.base_url = (base_url or s.ODDS_API_BASE_URL).rstrip("/")
        self.db_session_factory = db_session_factory
        self.client = client

    async def _get(self, path: str, params: Optional[dict] = None, ttl: int = 60) -> list | dict:
        p = dict(params or {})
        p["apiKey"] = self.api_key
        key = f"odds:{path}:{sorted({k: v for k, v in p.items() if k != 'apiKey'}.items())}"
        return await logged_request(
            self.provider_name, "GET", f"{self.base_url}{path}",
            params=p, cache_key=key, cache_ttl=ttl,
            db_session_factory=self.db_session_factory, client=self.client,
        ) or []

    async def get_odds(self, match_hint: Optional[str] = None,
                     sport_key: str = DEFAULT_SPORT_KEY) -> list[OddsSnapshotDTO]:
        return await self._fetch_odds(live=False, sport_key=sport_key)

    async def get_live_odds(self, match_hint: Optional[str] = None,
                            sport_key: str = DEFAULT_SPORT_KEY) -> list[OddsSnapshotDTO]:
        return await self._fetch_odds(live=True, sport_key=sport_key)

    async def _fetch_odds(self, live: bool, sport_key: str = DEFAULT_SPORT_KEY) -> list[OddsSnapshotDTO]:
        s = get_settings()
        data = await self._get(
            f"/sports/{sport_key}/odds",
            {"regions": s.ODDS_REGIONS, "markets": s.ODDS_MARKETS,
             "oddsFormat": "decimal", "dateFormat": "iso"},
            ttl=60 if live else 300,
        )
        out: list[OddsSnapshotDTO] = []
        events = data if isinstance(data, list) else []
        for event in events:
            if not isinstance(event, dict):
                continue
            for bk in event.get("bookmakers", []) or []:
                if not isinstance(bk, dict):
                    continue
                for mk in bk.get("markets", []) or []:
                    if not isinstance(mk, dict):
                        continue
                    sels = []
                    for oc in mk.get("outcomes", []) or []:
                        if not isinstance(oc, dict):
                            continue
                        name = OUTCOME_MAP.get(str(oc.get("name", "")), str(oc.get("name", "")).lower())
                        try:
                            price = float(oc.get("price", 0))
                        except (TypeError, ValueError):
                            continue
                        if price <= 1.0:
                            continue
                        point = oc.get("point")
                        sel = name if point is None else f"{name}_{point}"
                        sels.append(OddsSelectionDTO(selection=sel, odds=price,
                                                    point=float(point) if point is not None else None))
                    if not sels:
                        continue
                    ts = event.get("commence_time") or bk.get("last_update")
                    try:
                        ts_dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00")) if ts else None
                    except ValueError:
                        ts_dt = None
                    try:
                        commence = datetime.fromisoformat(
                            str(event.get("commence_time")).replace("Z", "+00:00")
                        ) if event.get("commence_time") else None
                    except ValueError:
                        commence = None
                    out.append(OddsSnapshotDTO(
                        bookmaker=str(bk.get("title", bk.get("key", ""))),
                        bookmaker_provider_id=str(bk.get("key", "")),
                        market_type=str(mk.get("key", "")),
                        timestamp=ts_dt or datetime.now(timezone.utc),
                        is_live=live, selections=sels,
                        event_id=str(event.get("id", "")) or None,
                        home_team=event.get("home_team"),
                        away_team=event.get("away_team"),
                        commence_time=commence,
                    ))
        return out

    async def get_markets(self) -> list[str]:
        return get_settings().ODDS_MARKETS.split(",")

    async def get_bookmakers(self) -> list[str]:
        return []
