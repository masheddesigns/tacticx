"""Formal provider capability representation (Phase 19).

Capabilities are tri-state evidence markers, never bare booleans:
MEASURED (observed in a real response), DOCUMENTED (declared by the
adapter/source docs, not yet observed), UNKNOWN (not yet probed),
UNAVAILABLE (probed and absent). No field is required to be supported —
absence is recorded, not penalized, unless the qualification level needs it.
"""
from __future__ import annotations

from typing import Dict, List

from pydantic import BaseModel, Field

MEASURED = "measured"
DOCUMENTED = "documented"
UNKNOWN = "unknown"
UNAVAILABLE = "unavailable"

EVIDENCE_STATES = (MEASURED, DOCUMENTED, UNKNOWN, UNAVAILABLE)


class ProviderCapabilities(BaseModel):
    source: str = ""
    provider_version: str = ""
    authentication_status: str = UNKNOWN
    fixtures: str = UNKNOWN
    results: str = UNKNOWN
    live_status: str = UNKNOWN
    kickoff_time: str = UNKNOWN
    venue: str = UNKNOWN
    teams: str = UNKNOWN
    team_ids: str = UNKNOWN
    competition_support: Dict[str, str] = Field(default_factory=dict)
    season_support: Dict[str, str] = Field(default_factory=dict)
    statistics: str = UNKNOWN
    shots: str = UNKNOWN
    xg: str = UNKNOWN
    events: str = UNKNOWN
    lineups: str = UNKNOWN
    players: str = UNKNOWN
    odds: str = UNKNOWN
    effective_timestamp: str = UNKNOWN
    retrieved_timestamp: str = UNKNOWN
    pagination: str = UNKNOWN
    rate_limits: str = UNKNOWN
    historical_access: str = UNKNOWN
    current_season_access: str = UNKNOWN
    licensing_notes: str = ""

    def measured_fields(self) -> List[str]:
        return [name for name, value in self.model_dump().items()
                if value == MEASURED and name not in ("source",)]

    def to_evidence(self) -> Dict[str, str]:
        out = {name: value for name, value in self.model_dump().items()
               if isinstance(value, str) and value in EVIDENCE_STATES}
        out["competition_support"] = {
            comp: state for comp, state in self.competition_support.items()
            if state in EVIDENCE_STATES} or {"_": UNKNOWN}
        out["season_support"] = {
            season: state for season, state in self.season_support.items()
            if state in EVIDENCE_STATES} or {"_": UNKNOWN}
        return out


def from_declared(source: str, declared: Dict[str, bool],
                  provider_version: str = "") -> ProviderCapabilities:
    """Seed capabilities from an adapter's declared SourceCapabilities.

    Declared support maps to DOCUMENTED (never MEASURED) — measurement
    requires an observed response.
    """
    mapping = {
        "fixtures": "fixtures", "match_detail": None, "standings": None,
        "odds_prematch": "odds", "odds_live": "odds",
        "historical_bulk": "historical_access",
        "leagues": "competition_support", "teams": "teams",
    }
    caps = ProviderCapabilities(source=source,
                                provider_version=provider_version)
    for declared_name, value in (declared or {}).items():
        target = mapping.get(declared_name)
        if target is None or not value:
            continue
        if target in ("competition_support",):
            continue  # populated per-competition during qualification
        setattr(caps, target, DOCUMENTED)
    return caps
