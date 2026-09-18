"""Feature/source-specific freshness policies (Phase 10).

No universal threshold: standings, form, membership, lineups and odds age
differently. Each policy defines fresh_until_days / stale_until_days /
expired_after_days plus what unknown timing means. All thresholds live in
app configuration (documented here by reference) and are overridable.
"""
from __future__ import annotations

from typing import Dict, Optional

# family -> (fresh_days, stale_days, description). Beyond stale_days the
# state is expired; unknown effective_at is always "unknown", never fresh.
FRESHNESS_POLICIES: Dict[str, Dict] = {
    "standings": {"fresh_days": 7, "stale_days": 30,
                  "note": "League tables move weekly; month-old tables expired."},
    "team_form": {"fresh_days": 14, "stale_days": 90,
                  "note": "Form over recent matchdays; a quarter without data expired."},
    "player_form": {"fresh_days": 30, "stale_days": 365,
                    "note": "Player form decays slower; a year without data expired."},
    "squad_membership": {"fresh_days": 90, "stale_days": 365,
                         "note": "Squads turn over per window; year-old membership expired."},
    "lineup": {"fresh_days": 30, "stale_days": 365,
               "note": "Lineup continuity needs same-season rows; older is stale."},
    "odds": {"fresh_days": 1, "stale_days": 7,
             "note": "Odds move intraday; week-old prices expired for pre-match use."},
    "xg": {"fresh_days": 30, "stale_days": 365,
           "note": "xG model outputs age with team personnel; year-old expired."},
    "default": {"fresh_days": 30, "stale_days": 365,
                "note": "Fallback policy when no family policy exists."},
}

STATE_FRESH, STATE_STALE, STATE_EXPIRED, STATE_UNKNOWN = (
    "fresh", "stale", "expired", "unknown")


def classify_freshness(family: str, age_days_value: Optional[float]) -> Dict:
    """fresh | stale | expired | unknown for one observation age."""
    policy = FRESHNESS_POLICIES.get(family, FRESHNESS_POLICIES["default"])
    if age_days_value is None:
        return {"state": STATE_UNKNOWN, "family": family,
                "policy": policy, "age_days": None,
                "reason": "effective_at unknown: freshness unknowable"}
    age = age_days_value
    if age <= policy["fresh_days"]:
        state = STATE_FRESH
    elif age <= policy["stale_days"]:
        state = STATE_STALE
    else:
        state = STATE_EXPIRED
    return {"state": state, "family": family, "policy": policy,
            "age_days": round(age, 2)}
