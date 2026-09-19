"""Field-specific source authority (Phase 19).

No global source A > source B rule. Each field names its authoritative
source(s) with a priority score; a provider may lead on one field and be
supplementary on another. Every rule is explicit, persisted, and reported.
"""
from __future__ import annotations

from typing import Dict, List, Optional

# field -> [(source_id, priority)] — higher wins; ties broken by source_id
# for determinism. Documented default; operators override via registry.
DEFAULT_FIELD_AUTHORITY: Dict[str, List[tuple]] = {
    "fixture_identity": [("api_football", 10)],
    "kickoff": [("api_football", 10)],
    "status": [("api_football", 10)],
    "result": [("api_football", 10), ("football_data_co_uk", 5)],
    "statistics": [("football_data_co_uk", 10)],
    "events": [("api_football", 10)],
    "lineups": [("api_football", 10)],
    "players": [("api_football", 10)],
    "xg": [],
    "odds": [("odds_api", 10)],
    "closing_odds": [("football_data_co_uk", 10)],
}


def authority_for(field: str,
                  overrides: Optional[Dict[str, List[tuple]]] = None) -> List[tuple]:
    """Ordered [(source_id, priority)] for a field, deterministic."""
    table = dict(DEFAULT_FIELD_AUTHORITY)
    if overrides:
        table.update(overrides)
    ranked = sorted(table.get(field, []), key=lambda item: (-item[1], item[0]))
    return ranked


def authoritative_source(field: str,
                         overrides: Optional[Dict[str, List[tuple]]] = None
                         ) -> Optional[str]:
    ranked = authority_for(field, overrides)
    return ranked[0][0] if ranked else None


def describe() -> Dict[str, List[tuple]]:
    return {field: authority_for(field) for field in sorted(DEFAULT_FIELD_AUTHORITY)}
