"""Transparent team aggregation helpers (Phase 9).

Every aggregate retains contributors + method metadata. Concentration uses
shares of counted events (descriptive, never causal).
"""
from __future__ import annotations

from typing import Dict, List


def concentration(values: List[float]) -> Dict:
    """Share of the top contributor + top-3 share over a non-negative vector."""
    total = sum(values)
    if total <= 0 or not values:
        return {"available": False,
                "reason": "no counted events; concentration undefined, not zero"}
    ordered = sorted(values, reverse=True)
    return {"available": True,
            "top_contributor_share": round(ordered[0] / total, 4),
            "top3_share": round(sum(ordered[:3]) / total, 4),
            "n_contributors": sum(1 for v in values if v > 0)}


def regulars(form_players: Dict, min_appearances: int = 3) -> Dict:
    """Players meeting the regular-contributor sample gate."""
    return {k: v for k, v in form_players.items()
            if v.get("matches_played", 0) >= min_appearances
            and not v.get("unresolved", False)}
