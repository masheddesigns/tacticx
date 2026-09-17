"""Probability math: validation, implied probability, overround, no-vig.

Version: market_probability_v1. Methodology changes must bump the version,
never silently rewrite historical outputs.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

MARKET_PROBABILITY_V1 = "market_probability_v1"

# Complete selection sets per market. Totals group by line (point); other
# markets are complete only with their full set. Unknown markets report
# completeness "unknown" and never get an overround.
COMPLETE_SETS: Dict[str, set] = {
    "h2h": {"home", "draw", "away"},
}

SUSPICIOUS_PRICE = 1000.0


def validate_price(price) -> Tuple[bool, str]:
    """Decimal odds must satisfy price > 1.0. Rejected, never repaired."""
    try:
        value = float(price)
    except (TypeError, ValueError):
        return False, f"not a number: {price!r}"
    if value != value:  # NaN
        return False, "price is NaN"
    if not value > 1.0:
        return False, f"decimal odds must be > 1.0: {price!r}"
    return True, ""


def price_warning(price: float) -> Optional[str]:
    if price > SUSPICIOUS_PRICE:
        return f"suspicious price above {SUSPICIOUS_PRICE}: {price!r}"
    return None


def implied_probability(price: float) -> float:
    """Raw implied probability 1/odds. Includes the bookmaker margin."""
    return 1.0 / float(price)


def market_completeness(market: str, selections: List[str],
                        point=None) -> str:
    """complete | partial | insufficient | unknown.

    h2h needs home+draw+away. totals needs over+under at one line — callers
    must group totals rows by point first (a bare totals list mixes lines).
    """
    have = set(selections)
    if market == "h2h":
        need = COMPLETE_SETS["h2h"]
    elif market == "totals":
        stems = {s.split("_")[0] for s in have}
        if {"over", "under"} <= stems:
            return "complete"
        return "partial" if stems else "insufficient"
    else:
        return "unknown"
    if need <= have:
        return "complete"
    if have:
        return "partial"
    return "insufficient"


def overround(prices: Dict[str, float]) -> Tuple[Optional[float], Optional[float], str]:
    """(overround_probability, overround_percentage, calculation_version).

    Returns (None, None) unless the caller passes a COMPLETE market —
    a false overround from missing selections is never calculated.
    """
    if not prices:
        return None, None, MARKET_PROBABILITY_V1
    total = sum(1.0 / p for p in prices.values())
    return round(total, 6), round((total - 1.0) * 100.0, 4), MARKET_PROBABILITY_V1


def no_vig_probabilities(prices: Dict[str, float]) -> Tuple[Dict[str, float], str]:
    """Normalized market probabilities; sums to 1 by construction."""
    total = sum(1.0 / p for p in prices.values())
    if total <= 0:
        return {}, MARKET_PROBABILITY_V1
    return ({sel: round((1.0 / price) / total, 6) for sel, price in prices.items()},
            MARKET_PROBABILITY_V1)
