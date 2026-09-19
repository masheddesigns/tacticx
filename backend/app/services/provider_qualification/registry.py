"""Qualification-aware source registry (Phase 19).

Extends the Phase 1.6 adapter registry with declarative entries:
source_id, adapter factory, declared capabilities, supported
competitions/seasons, field authority, rate limit, priority, enabled flag
and qualification status. Prediction/intelligence code never branches on
provider names — it consumes the abstract contract only.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from app.services.provider_qualification.capabilities import ProviderCapabilities

# Qualification levels. Only A trusts a source for canonical fixtures.
LEVEL_A = "A"
LEVEL_B = "B"
LEVEL_C = "C"
LEVEL_D = "D"

LEVEL_DESCRIPTIONS = {
    LEVEL_A: "canonical fixture source",
    LEVEL_B: "supplementary source (stats/events/lineups/players/xG)",
    LEVEL_C: "market source (odds only, never fixture authority)",
    LEVEL_D: "rejected",
}


class SourceEntry:
    """Declarative registration for one source."""

    def __init__(self, source_id: str, adapter: Callable[..., Any],
                 capabilities: Optional[ProviderCapabilities] = None,
                 supported_competitions: Optional[List[str]] = None,
                 supported_seasons: Optional[List[str]] = None,
                 field_authority: Optional[Dict[str, int]] = None,
                 rate_limit_per_minute: Optional[int] = None,
                 priority: int = 100,
                 enabled: bool = True,
                 qualification_status: str = "unqualified") -> None:
        self.source_id = source_id
        self.adapter = adapter
        self.capabilities = capabilities or ProviderCapabilities(source=source_id)
        self.supported_competitions = list(supported_competitions or [])
        self.supported_seasons = list(supported_seasons or [])
        self.field_authority = dict(field_authority or {})
        self.rate_limit_per_minute = rate_limit_per_minute
        self.priority = priority
        self.enabled = enabled
        self.qualification_status = qualification_status

    def describe(self) -> Dict[str, Any]:
        return {
            "source_id": self.source_id,
            "capabilities": self.capabilities.to_evidence(),
            "supported_competitions": self.supported_competitions,
            "supported_seasons": self.supported_seasons,
            "field_authority": self.field_authority,
            "rate_limit_per_minute": self.rate_limit_per_minute,
            "rate_limit_known": self.rate_limit_per_minute is not None,
            "priority": self.priority,
            "enabled": self.enabled,
            "qualification_status": self.qualification_status,
            "level": LEVEL_DESCRIPTIONS.get(
                self.qualification_status if self.qualification_status in
                LEVEL_DESCRIPTIONS else "", ""),
        }


class QualificationRegistry:
    """source_id -> SourceEntry. Deterministic ordering by (priority, id)."""

    def __init__(self) -> None:
        self._entries: Dict[str, SourceEntry] = {}

    def register_source(self, source_id: str, adapter: Callable[..., Any],
                        **kwargs) -> SourceEntry:
        entry = SourceEntry(source_id, adapter, **kwargs)
        self._entries[source_id] = entry
        return entry

    def get(self, source_id: str) -> SourceEntry:
        if source_id not in self._entries:
            raise ValueError(f"unknown source: {source_id!r} "
                             f"(registered: {sorted(self._entries)})")
        return self._entries[source_id]

    def ordered(self, enabled_only: bool = True) -> List[SourceEntry]:
        entries = [e for e in self._entries.values()
                   if e.enabled or not enabled_only]
        return sorted(entries, key=lambda e: (e.priority, e.source_id))

    def set_qualification(self, source_id: str, status: str) -> SourceEntry:
        entry = self.get(source_id)
        entry.qualification_status = status
        return entry

    def describe(self) -> Dict[str, Any]:
        return {source_id: entry.describe()
                for source_id, entry in sorted(self._entries.items())}


REGISTRY = QualificationRegistry()


def register_source(source_id: str, adapter: Callable[..., Any],
                    **kwargs) -> SourceEntry:
    """Public registration point. TacticX core never calls adapters directly."""
    return REGISTRY.register_source(source_id, adapter, **kwargs)


def _default_entries() -> None:
    """Seed registry from measured Phase 18 knowledge (conservative)."""
    from app.services.provider_qualification.capabilities import ProviderCapabilities

    if REGISTRY._entries:
        return
    register_source(
        "api_football",
        lambda **kwargs: _resolve_adapter("football", "api_football", **kwargs),
        capabilities=ProviderCapabilities(
            source="api_football", fixtures="documented", results="documented",
            teams="documented", team_ids="documented",
            kickoff_time="documented", historical_access="documented",
            current_season_access="unavailable"),
        supported_competitions=["EPL", "LA_LIGA", "SERIE_A", "BUNDESLIGA",
                                "LIGUE_1"],
        supported_seasons=["2024"],
        field_authority={"fixture_identity": 10, "kickoff": 10,
                         "status": 10, "result": 10},
        rate_limit_per_minute=None,  # unknown -> conservative defaults apply
        priority=10, enabled=True, qualification_status="unqualified")
    register_source(
        "odds_api",
        lambda **kwargs: _resolve_adapter("odds", "odds_api", **kwargs),
        capabilities=ProviderCapabilities(
            source="odds_api", odds="documented",
            current_season_access="documented"),
        supported_competitions=[],
        supported_seasons=[],
        field_authority={"odds": 10},
        rate_limit_per_minute=None,
        priority=50, enabled=True, qualification_status="unqualified")
    register_source(
        "football_data_co_uk",
        lambda **kwargs: _resolve_adapter("football", "football_data_co_uk",
                                          **kwargs),
        capabilities=ProviderCapabilities(
            source="football_data_co_uk", fixtures="documented",
            results="documented", statistics="documented",
            historical_access="documented"),
        supported_competitions=["EPL", "LA_LIGA", "SERIE_A", "BUNDESLIGA",
                                "LIGUE_1"],
        supported_seasons=["2024"],
        field_authority={"closing_odds": 10, "result": 5},
        rate_limit_per_minute=None,
        priority=20, enabled=True, qualification_status="unqualified")


def _resolve_adapter(axis: str, name: str, **kwargs):
    from app.services.sources import registry as registry_mod

    getter = {"football": registry_mod.get_football_registry,
              "odds": registry_mod.get_odds_registry,
              "historical": registry_mod.get_historical_registry}[axis]
    return getter().resolve(name, **kwargs)


def get_registry() -> QualificationRegistry:
    _default_entries()
    return REGISTRY


def reset_registry() -> None:
    """Test helper: drop seeded entries so tests start deterministic."""
    REGISTRY._entries.clear()
