"""Walk-forward ensemble weight learning (Phase 4).

Weights are learned ONLY on training-period information: member predictions
are generated per match with that match's kickoff as cutoff (no future data),
then a deterministic grid search over the probability simplex minimizes
log-loss. Grid order is fixed; ties keep the first (lowest-index) weights,
so results are reproducible bit-for-bit.

Never use test-period outcomes to determine weights used for test predictions
— the walk-forward orchestrator enforces this by construction.
"""
from __future__ import annotations

import itertools
from typing import Dict, List, Optional, Tuple

import numpy as np

from app.services.backtesting import metrics as met


def simplex_grid(n_models: int, step: float = 0.1) -> List[List[float]]:
    """Deterministic enumeration of weight vectors summing to 1."""
    if n_models <= 0:
        raise ValueError("need at least one model")
    if n_models == 1:
        return [[1.0]]
    units = int(round(1.0 / step))
    grids = []
    for combo in itertools.product(range(units + 1), repeat=n_models - 1):
        if sum(combo) > units:
            continue
        last = units - sum(combo)
        grids.append([c / units for c in (*combo, last)])
    return grids


def blend_probabilities(member_probs: List[List[List[float]]],
                        weights: List[float]) -> List[List[float]]:
    """Weighted average of member 1X2 vectors, renormalized per row."""
    arr = np.asarray(member_probs, dtype=float)  # (models, matches, 3)
    weights_arr = np.asarray(weights, dtype=float)
    blended = (arr * weights_arr[:, None, None]).sum(axis=0)
    totals = blended.sum(axis=1, keepdims=True)
    totals[totals <= 0] = 1.0
    return (blended / totals).tolist()


def learn_weights(member_probs: List[List[List[float]]], actual: List[int],
                  step: float = 0.1) -> Tuple[List[float], Dict]:
    """Grid-search simplex weights minimizing log-loss. Returns
    (weights, diagnostics). Empty sample raises ValueError (no fabrication)."""
    if not actual:
        raise ValueError("no training outcomes to learn weights from")
    if any(len(p) != len(actual) for p in member_probs):
        raise ValueError("member prediction counts differ")
    best: Optional[List[float]] = None
    best_loss = float("inf")
    evaluated = 0
    for weights in simplex_grid(len(member_probs), step=step):
        blended = blend_probabilities(member_probs, weights)
        loss = met.multiclass_log_loss(np.asarray(blended), actual)
        evaluated += 1
        if loss < best_loss:
            best_loss = loss
            best = list(weights)
    assert best is not None
    return best, {"log_loss": round(best_loss, 6), "evaluated": evaluated,
                  "n_models": len(member_probs), "n_matches": len(actual)}
