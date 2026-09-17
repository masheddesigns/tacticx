"""Availability-based model regime selection (no test-outcome input)."""
from __future__ import annotations

from typing import Dict, List, Optional

MODEL_STATUS_REGISTRY: Dict[str, Dict] = {
    "elo_v1": {"features_required": ["results"], "training_method": "chronological Elo updates",
               "calibration": "empirical draw prior", "supported_outputs": ["1x2"],
               "data_requirements": ">=1 finished pre-cutoff match", "status": "validated"},
    "poisson_v1": {"features_required": ["results"], "training_method": "pre-cutoff MLE-style rates",
                   "calibration": "none", "supported_outputs": ["1x2", "goals", "totals", "btts", "scores"],
                   "data_requirements": ">=5 matches/team, >=2 per venue", "status": "validated"},
    "poisson_v1-xg": {"features_required": ["results", "xg"], "training_method": "pre-cutoff rates + xG blend",
                      "calibration": "none", "supported_outputs": ["1x2", "goals", "totals", "btts", "scores"],
                      "data_requirements": "poisson_v1 requirements + >=3 xG obs/team", "status": "validated"},
    "advanced_v1": {"features_required": ["results", "form", "rest"], "training_method": "walk-forward softmax fit",
                    "calibration": "optional temperature (train-only)", "supported_outputs": ["1x2"],
                    "data_requirements": "fitted coefficients + feature coverage", "status": "experimental"},
    "advanced_v1-xg": {"features_required": ["results", "form", "rest", "xg"], "training_method": "walk-forward softmax fit",
                       "calibration": "optional temperature (train-only)", "supported_outputs": ["1x2"],
                       "data_requirements": "advanced_v1 requirements + xG-eligible rows", "status": "experimental"},
    "advanced_goal_v1": {"features_required": ["results"], "training_method": "pre-cutoff rates + shrinkage",
                         "calibration": "none", "supported_outputs": ["1x2", "goals", "totals", "btts", "scores"],
                         "data_requirements": ">=5 matches/team", "status": "experimental"},
    "ensemble_v1": {"features_required": ["results"], "training_method": "fixed equal weights",
                    "calibration": "none", "supported_outputs": ["1x2", "goals", "totals", "btts", "scores"],
                    "data_requirements": "member coverage", "status": "validated"},
    "ensemble_v2": {"features_required": ["results"], "training_method": "walk-forward learned weights",
                    "calibration": "optional temperature (train-only)", "supported_outputs": ["1x2", "goals", "totals", "btts", "scores"],
                    "data_requirements": "validation window with member coverage", "status": "experimental"},
    "calibration_v1": {"features_required": [], "training_method": "temperature scaling on train window",
                       "calibration": "self", "supported_outputs": ["1x2 (rescaled)"],
                       "data_requirements": ">=50 train outcomes", "status": "experimental"},
    "baseline_v1": {"features_required": ["results"], "training_method": "empirical frequencies",
                    "calibration": "none", "supported_outputs": ["1x2"],
                    "data_requirements": ">=1 finished pre-cutoff match", "status": "validated"},
}


def select_model(availability: Dict, xg_eligible: bool = False,
                 advanced_fitted: bool = False) -> Dict:
    """Deterministic regime policy from data availability, fixed BEFORE any
    test evaluation. Never consults test outcomes.

    Returns {"model": name, "reason": str}. The production default stays
    ensemble_v1; this policy only routes to richer pathways when their
    inputs exist.
    """
    goals_ok = bool(availability.get("goals"))
    if not goals_ok:
        return {"model": "baseline_v1",
                "reason": "insufficient goal history; empirical prior only"}
    if xg_eligible:
        return {"model": "poisson_v1-xg",
                "reason": "xG history meets minimum; xG-blended Poisson available"}
    if advanced_fitted:
        return {"model": "advanced_v1",
                "reason": "advanced features covered and coefficients fitted"}
    return {"model": "ensemble_v1",
            "reason": "default statistical ensemble; no richer pathway eligible"}


def default_policy() -> Dict:
    """Documented default policy (informational; defaults are not changed
    automatically — see Phase 5 report)."""
    return {
        "default": "ensemble_v1",
        "xg_pathway": "poisson_v1-xg when xG history meets minimum, else poisson_v1",
        "advanced_pathway": "advanced_v1 only when fitted on a separate train window",
        "market_role": "independent benchmark only, never an ensemble input",
        "note": "Policy fixed from availability evidence, not test performance.",
    }
