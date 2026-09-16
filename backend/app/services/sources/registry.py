"""Source registry (Phase 1.6).

Sources are chosen by configuration, never hard-coded into the pipeline:

    FOOTBALL_SOURCE_PRIMARY=football_data_co_uk
    FOOTBALL_SOURCE_FALLBACK=api_football
    ODDS_SOURCE_PRIMARY=football_data_co_uk
    ODDS_SOURCE_FALLBACK=odds_api
    HISTORICAL_SOURCE=csv

APIs remain available as fallback/validation sources.
"""
from __future__ import annotations

from typing import Optional

from app.config import get_settings
from app.logging_config import get_logger
from app.services.sources.base import (
    DataSource,
    FootballDataSource,
    HistoricalDataSource,
    OddsDataSource,
)

log = get_logger(__name__)


class SourceRegistry:
    """Name -> factory registry for one source axis."""

    def __init__(self, axis: str):
        self.axis = axis
        self._factories: dict[str, callable] = {}

    def register(self, name: str, factory: callable) -> None:
        self._factories[name.lower()] = factory

    def available(self) -> list[str]:
        return sorted(self._factories)

    def resolve(self, name: str, **kwargs) -> DataSource:
        key = (name or "").lower()
        if key not in self._factories:
            raise ValueError(f"unknown {self.axis} source: {name!r} (available: {self.available()})")
        return self._factories[key](**kwargs)

    def resolve_chain(self, primary: str, fallback: str, **kwargs) -> list[DataSource]:
        """Primary first, fallback appended when configured and different."""
        chain = [self.resolve(primary, **kwargs)]
        if fallback and fallback.lower() != primary.lower():
            try:
                chain.append(self.resolve(fallback, **kwargs))
            except ValueError as exc:
                log.warning("fallback source misconfigured: %s", exc)
        return chain


FootballSourceRegistry = SourceRegistry("football")
OddsSourceRegistry = SourceRegistry("odds")
HistoricalSourceRegistry = SourceRegistry("historical")

_football_registry: Optional[SourceRegistry] = None
_odds_registry: Optional[SourceRegistry] = None
_historical_registry: Optional[SourceRegistry] = None


def _build_football_registry() -> SourceRegistry:
    from app.services.sources.football.api_football_source import ApiFootballSource
    from app.services.sources.football.football_data_co_uk import FootballDataCoUkSource
    from app.services.sources.football.statsbomb import StatsBombSource
    from app.services.sources.historical.csv_source import CsvFileSource

    reg = SourceRegistry("football")
    reg.register("api_football", ApiFootballSource)
    reg.register("football_data_co_uk", FootballDataCoUkSource)
    reg.register("statsbomb", StatsBombSource)
    reg.register("csv", CsvFileSource)
    return reg


def _build_odds_registry() -> SourceRegistry:
    from app.services.sources.football.football_data_co_uk import FootballDataCoUkSource
    from app.services.sources.historical.csv_source import CsvFileSource
    from app.services.sources.odds.odds_api_source import OddsApiSource

    reg = SourceRegistry("odds")
    reg.register("odds_api", OddsApiSource)
    reg.register("football_data_co_uk", FootballDataCoUkSource)
    reg.register("csv", CsvFileSource)  # closing lines from dataset files
    return reg


def _build_historical_registry() -> SourceRegistry:
    from app.services.sources.football.football_data_co_uk import FootballDataCoUkSource
    from app.services.sources.football.statsbomb import StatsBombSource
    from app.services.sources.historical.csv_source import CsvFileSource

    reg = SourceRegistry("historical")
    reg.register("csv", CsvFileSource)
    reg.register("football_data_co_uk", FootballDataCoUkSource)
    reg.register("statsbomb", StatsBombSource)
    return reg


def get_football_registry() -> SourceRegistry:
    global _football_registry
    if _football_registry is None:
        _football_registry = _build_football_registry()
    return _football_registry


def get_odds_registry() -> SourceRegistry:
    global _odds_registry
    if _odds_registry is None:
        _odds_registry = _build_odds_registry()
    return _odds_registry


def get_historical_registry() -> SourceRegistry:
    global _historical_registry
    if _historical_registry is None:
        _historical_registry = _build_historical_registry()
    return _historical_registry


def reset_registries() -> None:
    """Test helper: drop cached registries so re-registration takes effect."""
    global _football_registry, _odds_registry, _historical_registry
    _football_registry = _odds_registry = _historical_registry = None


def football_source_chain(**kwargs) -> list[FootballDataSource]:
    s = get_settings()
    return get_football_registry().resolve_chain(
        s.FOOTBALL_SOURCE_PRIMARY, s.FOOTBALL_SOURCE_FALLBACK, **kwargs)


def odds_source_chain(**kwargs) -> list[OddsDataSource]:
    s = get_settings()
    return get_odds_registry().resolve_chain(
        s.ODDS_SOURCE_PRIMARY, s.ODDS_SOURCE_FALLBACK, **kwargs)


def historical_source(name: str = "", **kwargs) -> HistoricalDataSource:
    s = get_settings()
    return get_historical_registry().resolve(name or s.HISTORICAL_SOURCE, **kwargs)
