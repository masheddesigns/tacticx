from __future__ import annotations

from app.services.sources.football.api_football_source import ApiFootballSource  # noqa: F401
from app.services.sources.football.football_data_co_uk import (  # noqa: F401
    DIVISIONS,
    FootballDataCoUkSource,
    season_segment,
    season_url,
)
from app.services.sources.football.statsbomb import (  # noqa: F401
    COMPETITIONS as STATSBOMB_COMPETITIONS,
    StatsBombSource,
    sb_season_name,
    season_date_range,
)

__all__ = [
    "ApiFootballSource",
    "DIVISIONS",
    "FootballDataCoUkSource",
    "STATSBOMB_COMPETITIONS",
    "StatsBombSource",
    "sb_season_name",
    "season_date_range",
    "season_segment",
    "season_url",
]
