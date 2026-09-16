"""The Odds API as a source-agnostic OddsDataSource (Phase 1.6).

Thin wrapper around the existing OddsApiProvider. Markets exposed are exactly
what the provider supplies (h2h/totals family) — never invented.
"""
from __future__ import annotations

from app.config import get_settings
from app.services.odds.odds_api import DEFAULT_SPORT_KEY, LEAGUE_SPORT_KEYS, OddsApiProvider
from app.services.scraping.framework import utcnow
from app.services.sources.base import OddsDataSource, SourceCapabilities
from app.services.sources.normalized import (
    NormalizedOddsSelection,
    NormalizedOddsSnapshot,
    Provenance,
)


class OddsApiSource(OddsDataSource):
    source_name = "odds_api"
    capabilities = SourceCapabilities(odds_prematch=True, odds_live=True)

    PARSER = "odds_api_parser_v1"

    def __init__(self, api_key: str = "", base_url: str = "", db_session_factory=None,
                 client=None, **kwargs):
        self.provider = OddsApiProvider(api_key=api_key, base_url=base_url,
                                        db_session_factory=db_session_factory, client=client)

    def check(self) -> dict:
        s = get_settings()
        return {"source": self.source_name,
                "configured": bool(s.ODDS_API_KEY.strip()),
                "role": "fallback/validation (quota-limited)"}

    async def get_odds_snapshots(self, league_code: str = "", season: str = "",
                                 live: bool = False) -> list[NormalizedOddsSnapshot]:
        sport = LEAGUE_SPORT_KEYS.get((league_code or "").upper(), DEFAULT_SPORT_KEY)
        dtos = await self.provider.get_live_odds(sport_key=sport) if live else \
            await self.provider.get_odds(sport_key=sport)
        out = []
        for dto in dtos:
            now = utcnow()
            out.append(NormalizedOddsSnapshot(
                league_code=league_code, season=season,
                home_team=dto.home_team or "", away_team=dto.away_team or "",
                kickoff_at=dto.commence_time, market=dto.market_type,
                timestamp=dto.timestamp, collected_at=dto.timestamp, is_live=dto.is_live,
                source=self.source_name, source_event_id=dto.event_id or "",
                selections=[
                    NormalizedOddsSelection(
                        selection=s.selection, price=s.odds, point=s.point,
                        bookmaker=dto.bookmaker, bookmaker_id=dto.bookmaker_provider_id)
                    for s in dto.selections
                ],
                provenance=Provenance(
                    source=self.source_name, source_record_id=dto.event_id or "",
                    collected_at=now, effective_at=now if live else None,
                    parser_version=self.PARSER,
                    temporal_quality="verified" if live else "estimated")))
        return out

    def supported_markets(self) -> list[str]:
        return [m for m in get_settings().ODDS_MARKETS.split(",") if m.strip()]
