"""Model-vs-market comparison (Phase 3).

Analytical descriptors only — never betting recommendations. Disagreement
is a measured difference in probability estimates, not a signal that the
market is wrong, and movement is never interpreted as insider/sharp/manipulated.
"""
from __future__ import annotations

from typing import Dict

from app.config import get_settings

COMPARISON_V1 = "model_market_comparison_v1"


def probability_differences(model_probs: Dict[str, float],
                            market_probs: Dict[str, float]) -> Dict[str, Dict[str, float]]:
    """Per-outcome absolute and relative differences (model minus market)."""
    out = {}
    for outcome, model_p in model_probs.items():
        market_p = market_probs.get(outcome)
        if market_p is None:
            continue
        absolute = model_p - market_p
        relative = (absolute / market_p) if market_p else None
        out[outcome] = {
            "model": round(model_p, 6),
            "market": round(market_p, 6),
            "absolute_difference": round(absolute, 6),
            "relative_difference": round(relative, 6) if relative is not None else None,
        }
    return out


def agreement_label(differences: Dict[str, Dict[str, float]],
                    model_probs: Dict[str, float],
                    market_probs: Dict[str, float]) -> str:
    """strong|moderate agreement, neutral, moderate|strong disagreement.

    Thresholds come from configuration (never hidden in code). Direction
    comes from whether both sides rank the same outcome first; magnitude
    from the largest absolute difference.
    """
    settings = get_settings()
    neutral = settings.MODEL_MARKET_NEUTRAL_THRESHOLD
    strong = settings.MODEL_MARKET_STRONG_THRESHOLD
    if not differences:
        return "neutral"
    peak = max(abs(d["absolute_difference"]) for d in differences.values())
    model_top = max(model_probs, key=lambda k: model_probs[k]) if model_probs else None
    market_top = max(market_probs, key=lambda k: market_probs[k]) if market_probs else None
    same_winner = model_top is not None and model_top == market_top
    if peak <= neutral:
        return "strong_agreement" if same_winner else "neutral"
    if peak <= strong:
        return "moderate_agreement" if same_winner else "moderate_disagreement"
    return "moderate_disagreement" if same_winner else "strong_disagreement"


def compare(model_probs: Dict[str, float], market_probs: Dict[str, float]) -> Dict:
    """Full comparison payload: differences + agreement descriptor."""
    differences = probability_differences(model_probs, market_probs)
    return {
        "differences": differences,
        "agreement": agreement_label(differences, model_probs, market_probs),
        "calculation_version": COMPARISON_V1,
        "note": ("Descriptive difference between two independent estimates. "
                 "Not a recommendation of any kind."),
    }
