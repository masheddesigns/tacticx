"""Provider factory — implementations chosen by config, never hard-coded."""
from __future__ import annotations

from app.config import get_settings
from app.services.base import FootballDataProvider, OddsProvider
from app.services.football.api_football import ApiFootballProvider
from app.services.odds.odds_api import OddsApiProvider


def get_football_provider(**kwargs) -> FootballDataProvider:
    name = (kwargs.pop("name", "") or get_settings().FOOTBALL_PROVIDER).lower()
    if name == "api_football":
        return ApiFootballProvider(**kwargs)
    raise ValueError(f"unknown football provider: {name}")


def get_odds_provider(**kwargs) -> OddsProvider:
    name = (kwargs.pop("name", "") or get_settings().ODDS_PROVIDER).lower()
    if name == "odds_api":
        return OddsApiProvider(**kwargs)
    raise ValueError(f"unknown odds provider: {name}")
