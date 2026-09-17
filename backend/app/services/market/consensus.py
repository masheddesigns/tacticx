"""Multi-bookmaker consensus (Phase 3).

Methodology (documented choice): aggregate at the PROBABILITY level, not by
averaging decimal odds. Each bookmaker's complete market becomes no-vig
probabilities; the consensus is the median (default), mean, or trimmed mean
across bookmakers. Median is the robust default: one stale/outlier book
cannot drag it.

Version: market_consensus_v1.
"""
from __future__ import annotations

import statistics
from typing import Dict, List, Optional

from app.config import get_settings

MARKET_CONSENSUS_V1 = "market_consensus_v1"


def aggregate(values: List[float], method: Optional[str] = None) -> Optional[float]:
    """Median (default) | mean | trimmed_mean (drops min/max when n>=4,
    otherwise median — trimming tiny samples would invent precision)."""
    if not values:
        return None
    method = (method or get_settings().ODDS_CONSENSUS_METHOD).lower()
    if method == "mean":
        return float(statistics.mean(values))
    if method == "trimmed_mean" and len(values) >= 4:
        trimmed = sorted(values)[1:-1]
        return float(statistics.mean(trimmed))
    return float(statistics.median(values))


def consensus(no_vig_by_bookmaker: Dict[str, Dict[str, float]],
              method: Optional[str] = None,
              min_bookmakers: Optional[int] = None) -> Dict:
    """Aggregate per-selection no-vig probabilities across bookmakers.

    Only selections present for a bookmaker participate; a consensus value
    is published per selection when >= min_bookmakers books quote it.
    """
    settings = get_settings()
    minimum = min_bookmakers if min_bookmakers is not None else settings.ODDS_CONSENSUS_MIN_BOOKMAKERS
    per_selection: Dict[str, List[float]] = {}
    for bookmaker, probs in no_vig_by_bookmaker.items():
        for selection, prob in probs.items():
            per_selection.setdefault(selection, []).append(prob)
    values = {}
    for selection, probs in per_selection.items():
        if len(probs) >= max(1, minimum):
            agg = aggregate(probs, method)
            if agg is not None:
                values[selection] = round(agg, 6)
    return {
        "values": values,
        "bookmakers_used": len(no_vig_by_bookmaker),
        "method": (method or settings.ODDS_CONSENSUS_METHOD).lower(),
        "calculation_version": MARKET_CONSENSUS_V1,
    }


def price_summary(prices: List[float]) -> Dict:
    """Best/worst/median/mean decimal prices within one time window."""
    if not prices:
        return {"best": None, "worst": None, "median": None, "mean": None, "count": 0}
    return {
        "best": max(prices),  # highest decimal price
        "worst": min(prices),
        "median": float(statistics.median(prices)),
        "mean": round(float(statistics.mean(prices)), 4),
        "count": len(prices),
    }
