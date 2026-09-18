"""Evaluation: 1X2 + goals + derived markets, identical populations (Phase 12).

Probability quality is primary (log loss, Brier, ECE); accuracy reported,
never alone. Goal MAE/RMSE where lambdas exist; derived-market Brier for
O/U and BTTS where probabilities derive mathematically. Paired comparison
against ensemble_v1 on identical test populations with bootstrap CIs.
"""
from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np

from app.services.backtesting import metrics as met
from app.services.evaluation.compare import compare_pair


def score_1x2(probs: List[List[float]], actual: List[int]) -> Dict:
    predicted = met.argmax_labels(probs)
    home = [p[0] for p in probs]
    actual_home = [1 if a == 0 else 0 for a in actual]
    return {
        "n": len(actual),
        "accuracy": round(sum(1 for p, a in zip(predicted, actual) if p == a)
                          / len(actual), 4) if actual else None,
        "log_loss": round(met.multiclass_log_loss(probs, actual), 4) if actual else None,
        "brier": round(met.multiclass_brier(probs, actual), 4) if actual else None,
        "ece_home": round(met.expected_calibration_error(home, actual_home), 4)
        if actual else None,
    }


def score_goals(pred_home: List[float], pred_away: List[float],
                act_home: List[float], act_away: List[float]) -> Dict:
    errors = [abs(p - a) for p, a in zip(pred_home + pred_away, act_home + act_away)]
    sq = [(p - a) ** 2 for p, a in zip(pred_home + pred_away, act_home + act_away)]
    n = len(errors)
    return {"n": n,
            "mae": round(sum(errors) / n, 4) if n else None,
            "rmse": round(float(np.sqrt(sum(sq) / n)), 4) if n else None}


def score_derived_markets(probs: List[List[float]], actual_totals: List[int],
                          actual_btts: List[int]) -> Dict:
    """Brier for O/U + BTTS derived from 1X2? No — derived markets need goal
    distributions. This scores total-goals and BTTS *expectations* only when
    the caller supplies them; otherwise reports unavailable (never faked)."""
    return {"status": "unavailable",
            "reason": "logreg candidates emit 1X2 only; derived-market scoring "
                      "applies to distributional models (poisson/ensemble)"}


def paired_vs_baseline(candidate_details: List[Dict],
                       baseline_details: List[Dict],
                       candidate_name: str, baseline_name: str = "ensemble_v1",
                       n_boot: int = 2000, seed: int = 7) -> Dict:
    return compare_pair(candidate_details, baseline_details,
                        candidate_name, baseline_name,
                        n_boot=n_boot, seed=seed)
