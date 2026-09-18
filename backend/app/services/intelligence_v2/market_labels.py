"""Model-vs-market interpretation labels (Phase 15).

Factual magnitude categories from configurable absolute-difference
thresholds. Labels carry no recommendation semantics: a "large_difference"
is an analytical observation, never an edge/bet/guarantee.
"""
from __future__ import annotations

from typing import Dict, List

from app.config import get_settings

SMALL, MODERATE, LARGE = "small_difference", "moderate_difference", "large_difference"


def thresholds() -> Dict[str, float]:
    settings = get_settings()
    return {"moderate": settings.MODEL_MARKET_NEUTRAL_THRESHOLD,
            "large": settings.MODEL_MARKET_STRONG_THRESHOLD}


def categorize(model_probs: Dict[str, float],
               market_probs: Dict[str, float]) -> Dict:
    """Per-outcome magnitude labels + overall label (max difference)."""
    bands = thresholds()
    per_outcome = {}
    peak = 0.0
    for outcome, model_p in (model_probs or {}).items():
        market_p = (market_probs or {}).get(outcome)
        if market_p is None or model_p is None:
            continue
        absolute = abs(model_p - market_p)
        peak = max(peak, absolute)
        per_outcome[outcome] = {
            "model": round(model_p, 6), "market": round(market_p, 6),
            "absolute_difference": round(model_p - market_p, 6),
            "magnitude": SMALL if absolute <= bands["moderate"] else (
                MODERATE if absolute <= bands["large"] else LARGE),
        }
    overall = SMALL if peak <= bands["moderate"] else (
        MODERATE if peak <= bands["large"] else LARGE)
    return {"per_outcome": per_outcome, "overall": overall,
            "peak_absolute_difference": round(peak, 6),
            "thresholds": bands,
            "note": "Magnitude labels are descriptive; not betting recommendations."}
